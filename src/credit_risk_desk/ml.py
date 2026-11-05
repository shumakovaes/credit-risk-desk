import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

FEATURES = ["account_age_days", "amount", "months", "payment", "tx_count_90d", "mean_balance_90d",
            "min_balance_90d", "negative_share_90d", "monthly_inflow_90d", "payment_to_inflow"]
FEATURE_VERSION = "strict_pre_day_90d_v1"


def make_pipeline():
    return Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                     ("scale", StandardScaler()),
                     ("model", LogisticRegression(C=1, max_iter=2000, random_state=42))])


def choose_threshold(y, probabilities, fn_cost=5.0, fp_cost=1.0):
    choices = np.unique(np.r_[0.0, probabilities, 1.0])
    def loss(t):
        pred = probabilities >= t
        return float(fn_cost * np.sum((y == 1) & ~pred) + fp_cost * np.sum((y == 0) & pred))
    threshold = min(choices, key=lambda t: (loss(t), -t))
    return float(threshold), loss(threshold)


def metrics(y, probabilities, threshold):
    pred = probabilities >= threshold
    observed, predicted = calibration_curve(y, probabilities, n_bins=5, strategy="quantile")
    return {"n": len(y), "bad_loans": int(np.sum(y)), "prevalence": float(np.mean(y)),
            "roc_auc": float(roc_auc_score(y, probabilities)),
            "average_precision": float(average_precision_score(y, probabilities)),
            "brier": float(brier_score_loss(y, probabilities)),
            "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "confusion_matrix_tn_fp_fn_tp": confusion_matrix(y, pred, labels=[0, 1]).ravel().tolist(),
            "calibration": {"mean_predicted": predicted.tolist(), "observed_fraction": observed.tolist()}}


def train(engine, destination):
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT mode FROM raw.dataset WHERE id=1")).scalar_one()
        if mode != "berka":
            raise ValueError("Training metrics are available only for the real Berka dataset, not synthetic demo data.")
        frame = pd.read_sql(text("SELECT * FROM analytics.training_mart ORDER BY loan_id"), conn)
    if not frame.account_id.is_unique or len(frame) < 60 or frame.target.value_counts().min() < 12:
        raise ValueError("Insufficient independent completed loans for a three-way stratified benchmark")
    trainval, test = train_test_split(frame, test_size=.2, random_state=42, stratify=frame.target)
    training, validation = train_test_split(trainval, test_size=.25, random_state=42, stratify=trainval.target)
    pipeline = make_pipeline().fit(training[FEATURES], training.target)
    val_p = pipeline.predict_proba(validation[FEATURES])[:, 1]
    threshold, cost = choose_threshold(validation.target.to_numpy(), val_p)
    test_p = pipeline.predict_proba(test[FEATURES])[:, 1]
    dummy = DummyClassifier(strategy="prior").fit(training[FEATURES], training.target)
    dummy_p = dummy.predict_proba(test[FEATURES])[:, 1]
    fingerprint = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
    version = hashlib.sha256((fingerprint + FEATURE_VERSION + sklearn.__version__ + "lr-C1-seed42-fn5-fp1").encode()).hexdigest()[:12]
    report = {
        "model_version": version, "feature_version": FEATURE_VERSION, "sklearn_version": sklearn.__version__,
        "dataset": "Berka completed A/B loans", "dataset_sha256": fingerprint,
        "target": "B=1: completed contract with unpaid debt; A=0: completed without problems",
        "not_a_horizon_pd": True,
        "split": "60/20/20 stratified by target, unique accounts, seed=42; retrospective benchmark, not a temporal deployment backtest",
        "split_ids": {name: sorted(part.loan_id.tolist()) for name, part in [("train", training), ("validation", validation), ("test", test)]},
        "split_counts": {name: {"n": len(part), "bad": int(part.target.sum())} for name, part in [("train", training), ("validation", validation), ("test", test)]},
        "threshold": threshold, "threshold_policy": {"false_negative_cost": 5, "false_positive_cost": 1,
            "units": "illustrative relative cost, not money", "selected_on": "validation", "validation_total_cost": cost},
        "validation": metrics(validation.target.to_numpy(), val_p, threshold),
        "test": metrics(test.target.to_numpy(), test_p, threshold),
        "dummy_test": metrics(test.target.to_numpy(), dummy_p, threshold),
        "features": FEATURES,
        "limitations": ["Small, historical, selected sample of granted and completed retail loans.",
            "Outcome ascertainment dates are not supplied; scheduled_end is not actual repayment date.",
            "Random split does not simulate label availability at a future launch date.",
            "Credit inflows are a transaction proxy, not verified income.",
            "Probabilities are uncalibrated logistic outputs; calibration bins are descriptive on a small test set.",
            "No claim of corporate lending performance, annual PD, or suitability for lending decisions."],
    }
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "report": report}, dest / "model.joblib")
    (dest / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def score(features, model_dir, mode):
    if mode == "demo":
        return {"available": False, "reason": "Демонстрационные данные: оценка ML отключена, метрики не рассчитываются."}
    path = Path(model_dir) / "model.joblib"
    if not path.exists():
        return {"available": False, "reason": "Модель ещё не обучена. Выполните credit-desk train."}
    # Only load artifacts generated locally by this application's training command.
    bundle = joblib.load(path)
    report, pipeline = bundle["report"], bundle["pipeline"]
    if report["feature_version"] != FEATURE_VERSION or report["sklearn_version"] != sklearn.__version__:
        return {"available": False, "reason": "Версия признаков или sklearn изменилась: переобучите модель."}
    x = pd.DataFrame([features])[FEATURES]
    probability = float(pipeline.predict_proba(x)[0, 1])
    transformed = pipeline[:-1].transform(x)[0]
    contributions = transformed * pipeline[-1].coef_[0]
    factors = sorted([{"feature": f, "value": features[f], "log_odds_contribution": float(v)}
                      for f, v in zip(FEATURES, contributions)], key=lambda r: abs(r["log_odds_contribution"]), reverse=True)
    return {"available": True, "score": probability, "threshold": report["threshold"],
            "requires_review": probability >= report["threshold"], "model_version": report["model_version"],
            "target": report["target"], "factors": factors,
            "interpretation": "Оценка неблагоприятного исхода завершённого розничного кредита; не годовая PD. Вклады в логиты — описание модели, не причины дефолта."}
