"""Validated, atomic dataset imports. Raw files stay untouched on disk."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from sqlalchemy import text

TABLES = ("account", "client", "disp", "loan", "trans", "district", "order", "card")
MIRROR = "https://raw.githubusercontent.com/jlacko/berka-dataset/master/"


def download(destination):
    """Explicit mirror; source and hashes are retained in a manifest."""
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"source": MIRROR, "files": {}}
    for name in TABLES:
        target = dest / f"{name}.asc"
        if not target.exists():
            with urlopen(MIRROR + target.name, timeout=120) as response:
                content = response.read()
            # A failed HTML response must never silently become a dataset.
            if b";" not in content[:1024] or b"<html" in content[:1024].lower():
                raise ValueError(f"Unexpected data format: {target.name}")
            tmp = target.with_suffix(".part")
            tmp.write_bytes(content)
            tmp.replace(target)
        manifest["files"][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f"Available: {target.name}", flush=True)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_dates(series):
    # Dataset years are in the 1990s; explicit century avoids Python's %y pivot.
    return pd.to_datetime("19" + series.astype(str).str.zfill(6), format="%Y%m%d", errors="raise").dt.date


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(frames):
    keys = {"clients": "client_id", "accounts": "account_id", "transactions": "trans_id", "loans": "loan_id"}
    for name, key in keys.items():
        df = frames[name]
        require(not df.empty, f"Empty table: {name}")
        require(not df.isna().any().any(), f"Missing required values: {name}")
        require(df[key].is_unique, f"Duplicate primary key: {name}.{key}")
    accounts, clients, tx, loans = (frames[n] for n in ("accounts", "clients", "transactions", "loans"))
    require(accounts.client_id.isin(clients.client_id).all(), "Unknown account owner")
    require(loans.account_id.is_unique, "Expected at most one historical loan per account")
    for frame in (tx, loans):
        require(frame.account_id.isin(accounts.account_id).all(), "Unknown account reference")
        require(np.isfinite(frame.amount).all() and (frame.amount >= 0).all(), "Invalid amount")
    require(np.isfinite(tx.balance).all(), "Invalid balance")
    require(tx.direction.isin(["credit", "debit"]).all(), "Unknown transaction direction")
    require(loans.status.isin(list("ABCD")).all(), "Unknown loan status")
    require((loans.amount > 0).all() and (loans.months > 0).all() and (loans.payment > 0).all(), "Non-positive loan parameters")
    opened = accounts.set_index("account_id").opened_at
    require((tx.booked_at >= tx.account_id.map(opened)).all(), "Transaction before account opening")
    require((loans.issued_at >= loans.account_id.map(opened)).all(), "Loan before account opening")


def read_berka(folder):
    folder = Path(folder)
    raw = {n: pd.read_csv(folder / f"{n}.asc", sep=";", encoding="utf-8", keep_default_na=False) for n in TABLES}
    for name, df in raw.items():
        key = "A1" if name == "district" else f"{name}_id"
        if key in df:
            require(df[key].is_unique, f"Duplicate raw key: {name}.{key}")
    a, c, d, l, t = (raw[n] for n in ("account", "client", "disp", "loan", "trans"))
    require(d.account_id.isin(a.account_id).all() and d.client_id.isin(c.client_id).all(), "Invalid disposition reference")
    require(d.type.isin(["OWNER", "DISPONENT"]).all(), "Unknown disposition type")
    owners = d[d.type == "OWNER"][["account_id", "client_id"]]
    require(owners.account_id.is_unique and len(owners) == len(a), "Each account must have exactly one owner")
    require(a.district_id.isin(raw["district"].A1).all() and c.district_id.isin(raw["district"].A1).all(), "Unknown district")
    require(raw["card"].disp_id.isin(d.disp_id).all(), "Unknown card disposition")
    require(raw["order"].account_id.isin(a.account_id).all(), "Unknown order account")
    accounts = a.merge(owners, on="account_id", validate="one_to_one").rename(columns={"date": "opened_at"})
    accounts["opened_at"] = parse_dates(accounts.opened_at)
    loans = l.rename(columns={"date": "issued_at", "duration": "months", "payments": "payment"})
    loans["issued_at"] = parse_dates(loans.issued_at)
    tx = t.rename(columns={"date": "booked_at", "k_symbol": "category"})
    tx["booked_at"] = parse_dates(tx.booked_at)
    tx["direction"] = tx["type"].map({"PRIJEM": "credit", "VYDAJ": "debit", "VYBER": "debit"})
    frames = {
        "clients": c[["client_id", "district_id"]],
        "accounts": accounts[["account_id", "client_id", "district_id", "opened_at"]],
        "loans": loans[["loan_id", "account_id", "issued_at", "amount", "months", "payment", "status"]],
        "transactions": tx[["trans_id", "account_id", "booked_at", "direction", "amount", "balance", "category"]],
    }
    manifest = {"source": str(folder.resolve()), "files": {
        n: {"rows": len(raw[n]), "sha256": hashlib.sha256((folder / f"{n}.asc").read_bytes()).hexdigest()} for n in TABLES}}
    validate(frames)
    return frames, manifest


def demo_frames(seed=42):
    """Fixed synthetic UI fixtures. Never used to claim predictive quality."""
    rng = np.random.default_rng(seed)
    clients, accounts, loans, tx = [], [], [], []
    for i in range(1, 61):
        clients.append({"client_id": i, "district_id": 1 + i % 8})
        accounts.append({"account_id": i, "client_id": i, "district_id": 1 + i % 8, "opened_at": date(2023, 1, 1)})
        balance = 12000.0
        income = float(14000 + i * 650)
        for month in range(24):
            day = date(2023 + month // 12, 1 + month % 12, 5)
            balance += income
            tx.append({"trans_id": len(tx) + 1, "account_id": i, "booked_at": day, "direction": "credit", "amount": income, "balance": round(balance, 2), "category": ""})
            expense = round(income * float(rng.uniform(.8, 1.08)), 2)
            balance -= expense
            tx.append({"trans_id": len(tx) + 1, "account_id": i, "booked_at": day + timedelta(days=10), "direction": "debit", "amount": expense, "balance": round(balance, 2), "category": ""})
        if i <= 48:
            months = [12, 24, 36, 48][i % 4]
            amount = float(24000 + i * 6000)
            loans.append({"loan_id": 1000 + i, "account_id": i, "issued_at": date(2024, 1, 1), "amount": amount, "months": months, "payment": round(amount / months, 2), "status": "ABCD"[i % 4]})
    return {"clients": pd.DataFrame(clients), "accounts": pd.DataFrame(accounts), "loans": pd.DataFrame(loans), "transactions": pd.DataFrame(tx)}


def load_dataset(engine, frames, mode, manifest):
    validate(frames)
    reference_date = max(frames["transactions"].booked_at) + timedelta(days=1)
    with engine.begin() as conn:
        # Serialize imports. Existing data are never silently overwritten.
        conn.execute(text("SELECT pg_advisory_xact_lock(673581)"))
        require(conn.execute(text("SELECT count(*) FROM raw.dataset")).scalar_one() == 0,
                "Database already contains a dataset. Use a separate empty database for another mode.")
        for name in ("clients", "accounts", "transactions", "loans"):
            df = frames[name]
            with conn.connection.driver_connection.cursor() as cursor:
                columns = ",".join(df.columns)
                with cursor.copy(f"COPY clean.{name} ({columns}) FROM STDIN") as copy:
                    for row in df.itertuples(index=False, name=None):
                        copy.write_row(row)
        conn.execute(text("INSERT INTO raw.dataset(id, mode, reference_date, manifest) VALUES (1, :mode, :ref, CAST(:manifest AS jsonb))"),
                     {"mode": mode, "ref": reference_date, "manifest": json.dumps(manifest)})
    return {"mode": mode, "reference_date": reference_date.isoformat(), "rows": {k: len(v) for k, v in frames.items()}}
