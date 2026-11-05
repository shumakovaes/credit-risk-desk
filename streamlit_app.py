"""Russian analyst interface. All data access goes through the HTTP API."""
import json
import os
from datetime import date

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
STATUS = {"checks_passed": "Проверки пройдены", "manual_review": "Ручная проверка", "rule_violation": "Нарушение правил"}
LOAN_STATUS = {"A": "A · Завершён без проблем", "B": "B · Завершён с долгом", "C": "C · Действует без просрочки", "D": "D · Действует с просрочкой"}
COLUMNS = {"loan_id": "Кредит", "account_id": "Счёт", "client_id": "Клиент", "district_id": "Регион",
           "issued_at": "Дата выдачи", "amount": "Сумма при выдаче, CZK", "months": "Срок, мес.",
           "payment": "Платёж, CZK", "status": "Статус", "opened_at": "Дата открытия",
           "booked_at": "Дата операции", "direction": "Направление", "balance": "Баланс, CZK",
           "category": "Категория", "trans_id": "Операция", "application_id": "ID заявки",
           "created_at": "Время проверки", "dataset_mode": "Режим данных"}
FEATURE_NAMES = {"account_age_days": "Возраст счёта, дней", "amount": "Сумма заявки", "months": "Срок",
                 "payment": "Платёж", "tx_count_90d": "Количество операций за 90 дней",
                 "mean_balance_90d": "Средний баланс после операций", "min_balance_90d": "Минимальный баланс",
                 "negative_share_90d": "Доля операций с отрицательным балансом",
                 "monthly_inflow_90d": "Среднемесячные поступления", "payment_to_inflow": "Платёж / поступления"}


def call(method, path, raw=False, **kwargs):
    try:
        response = httpx.request(method, API + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response.content if raw else response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except ValueError:
            detail = f"HTTP {exc.response.status_code}"
        st.error(f"Запрос не выполнен: {detail}")
    except httpx.RequestError:
        st.error("API недоступен. Запустите сервис и проверьте API_URL.")
    return None


def table(rows):
    if rows:
        frame = pd.DataFrame(rows)
        if "direction" in frame:
            frame["direction"] = frame.direction.map({"credit": "Поступление", "debit": "Списание"})
        if "status" in frame:
            frame["status"] = frame.status.map(lambda x: LOAN_STATUS.get(x, STATUS.get(x, x)))
        st.dataframe(frame.rename(columns=COLUMNS), hide_index=True, width="stretch")
    else:
        st.info("По выбранным условиям записей нет.")


def result_view(result):
    status = result["status"]
    message = STATUS[status]
    {"checks_passed": st.success, "manual_review": st.warning, "rule_violation": st.error}[status](message)
    a, b, c = st.columns(3)
    a.metric("Платёж в месяц", f"{result['calculation']['monthly_payment']:,.2f} CZK")
    burden = result["rules"]["payment_to_income"]
    b.metric("Нагрузка по заявленным данным", "Нет данных" if burden is None else f"{burden:.1%}")
    model = result["model"]
    c.metric("Оценка модели", f"{model['score']:.1%}" if model["available"] else "Не рассчитана")
    st.subheader("Бизнес-правила")
    checks = pd.DataFrame(result["rules"]["checks"])
    checks["code"] = checks.code.map({"amount": "Сумма кредита", "term": "Срок кредита", "available_limit": "Доступный лимит", "payment_to_income": "Долговая нагрузка", "history": "История счёта"})
    checks["status"] = checks.status.map({"passed": "Пройдено", "failed": "Нарушение", "unknown": "Нужны данные"})
    st.dataframe(checks.rename(columns={"code": "Правило", "status": "Результат", "reason": "Объяснение"}), hide_index=True, width="stretch")
    st.caption(f"Версия правил: {result['rules']['version']}")
    if model["available"]:
        st.subheader("Что повлияло на оценку модели")
        st.caption(f"Модель {model['model_version']} · Порог ручной проверки {model['threshold']:.1%}. {model['interpretation']}")
        factors = pd.DataFrame(model["factors"])
        factors["feature"] = factors.feature.map(FEATURE_NAMES)
        chart = px.bar(factors.sort_values("log_odds_contribution"), x="log_odds_contribution", y="feature", orientation="h",
                       color="log_odds_contribution", color_continuous_scale=["#117E74", "#DCE7EB", "#CC5A47"],
                       labels={"feature": "Признак", "log_odds_contribution": "Вклад в логит риска относительно среднего train"})
        chart.update_layout(showlegend=False, coloraxis_showscale=False, height=390)
        st.plotly_chart(chart, width="stretch")
    else:
        st.info(model["reason"])
    with st.expander("Признаки и дата расчёта"):
        st.caption(f"Только операции строго до {result['as_of']}; окно 90 дней.")
        st.json({FEATURE_NAMES[k]: v for k, v in result["features"].items()})
    st.caption(result["notice"])
    st.download_button("Скачать отчёт JSON", json.dumps(result, ensure_ascii=False, indent=2),
                       file_name=f"application-{result['application_id']}.json", mime="application/json")


st.set_page_config(page_title="Credit Risk Desk", page_icon="◈", layout="wide")
st.sidebar.title("◈ Credit Risk Desk")
st.sidebar.caption("Рабочее место кредитного аналитика")
page = st.sidebar.radio("Раздел", ["Портфель", "Карточка клиента", "Проверка заявки", "Калькулятор", "Журнал заявок"], label_visibility="collapsed")
meta = call("GET", "/metadata")
if meta is None:
    st.title("Credit Risk Desk")
    st.info("После запуска API здесь появятся портфель, карточки клиентов и проверка заявок.")
    st.stop()
reference = date.fromisoformat(meta["reference_date"])
demo = meta["mode"] == "demo"
st.sidebar.divider()
st.sidebar.markdown("**Синтетическая демонстрация**" if demo else "**Исторические данные Berka**")
st.sidebar.caption(f"Дата среза: {reference:%d.%m.%Y} · CZK")
st.sidebar.caption("Учебный проект · розничные кредиты")
if demo:
    st.info("ДЕМО · Все записи синтетические. ML отключён. Правила, расчёты и сохранение заявок работают.")
else:
    st.info("BERKA · Исторические розничные кредиты. Оценка модели не является годовой PD или решением о выдаче.")

if page == "Портфель":
    st.title("Кредитный портфель")
    st.caption("Обзор выданных кредитов и их статусов на момент формирования набора данных.")
    c1, c2 = st.columns(2)
    district = c1.selectbox("Регион", ["Все", *meta["districts"]])
    status = c2.selectbox("Статус кредита", ["Все", *LOAN_STATUS], format_func=lambda x: LOAN_STATUS.get(x, x))
    params = {}
    if district != "Все": params["district"] = district
    if status != "Все": params["status"] = status
    data = call("GET", "/portfolio", params=params)
    if data:
        a, b, c, d = st.columns(4)
        a.metric("Кредитов", data["loans"])
        b.metric("Сумма при выдаче, млн CZK", f"{data['original_amount_total'] / 1_000_000:,.2f}")
        c.metric("Завершено с долгом · B", data["status_counts"]["B"])
        d.metric("Действуют с просрочкой · D", data["status_counts"]["D"])
        st.caption("Сумма при выдаче не равна текущей задолженности. B и D относятся к разным стадиям кредита.")
        if data["items"]:
            left, right = st.columns([1, 1.5])
            counts = pd.DataFrame({"Статус": [LOAN_STATUS[s] for s in "ABCD"], "Кредитов": [data["status_counts"][s] for s in "ABCD"]})
            left.plotly_chart(px.bar(counts, x="Кредитов", y="Статус", orientation="h", color_discrete_sequence=["#117E74"]), width="stretch")
            frame = pd.DataFrame(data["items"])
            histogram = px.histogram(frame, x="amount", nbins=15, labels={"amount": "Сумма при выдаче, CZK"}, color_discrete_sequence=["#386B97"])
            histogram.update_yaxes(title_text="Кредитов")
            right.plotly_chart(histogram, width="stretch")
        table(data["items"])
        csv = call("GET", "/portfolio/export", params=params, raw=True)
        if csv is not None:
            st.download_button("Экспорт текущего среза CSV", csv, file_name=f"portfolio-{meta['mode']}.csv", mime="text/csv")

elif page == "Карточка клиента":
    st.title("Карточка клиента")
    q = st.text_input("Поиск по ID клиента или счёта", placeholder="Например, 1")
    clients = call("GET", "/clients", params={"q": q, "limit": 100})
    if clients:
        chosen = st.selectbox("Клиент и счёт", clients, format_func=lambda r: f"Клиент {r['client_id']} · счёт {r['account_id']} · регион {r['district_id']}")
        card = call("GET", f"/clients/{chosen['client_id']}")
        if card:
            st.subheader(f"Клиент №{chosen['client_id']}")
            st.caption("В базе нет имён. Отображаются счета, где клиент является владельцем.")
            table(card["accounts"])
            st.subheader("Кредиты")
            table(card["loans"])
            st.subheader("Последние операции · до 100 записей")
            table(card["recent_transactions"])
    else:
        st.info("Ничего не найдено. Уточните ID.")

elif page == "Проверка заявки":
    st.title("Проверка кредитной заявки")
    st.caption("Введите параметры кредита. История счёта и признаки для модели загрузятся автоматически.")
    with st.form("application_form"):
        a, b, c = st.columns(3)
        account = a.number_input("ID счёта", min_value=1, value=1, step=1)
        as_of = b.date_input("Дата оценки", value=reference, max_value=reference)
        amount = c.number_input("Сумма кредита, CZK", min_value=1.0, value=120000.0, step=1000.0)
        a, b, c = st.columns(3)
        months = a.number_input("Срок, месяцев", min_value=1, max_value=600, value=24, step=1)
        rate = b.number_input("Номинальная ставка, % годовых", min_value=0.0, max_value=100.0, value=12.0)
        has_info = c.checkbox("Доход, платежи и лимит известны", value=True)
        a, b, c = st.columns(3)
        income = a.number_input("Заявленный доход, CZK/мес.", min_value=1.0, value=30000.0)
        existing = b.number_input("Действующие платежи, CZK/мес.", min_value=0.0, value=2000.0)
        limit = c.number_input("Доступный лимит, CZK", min_value=0.0, value=200000.0)
        st.caption("Это введённые вами сведения. Банковская проверка дохода и лимита не имитируется.")
        submitted = st.form_submit_button("Проверить и сохранить", type="primary")
    if submitted:
        request = {"account_id": account, "as_of": as_of.isoformat(), "amount": amount, "months": months,
                   "annual_rate_pct": rate, "declared_monthly_income": income if has_info else None,
                   "existing_monthly_payments": existing if has_info else None, "available_limit": limit if has_info else None}
        st.session_state["evaluation"] = call("POST", "/applications/evaluate", json=request)
    if st.session_state.get("evaluation"):
        result_view(st.session_state["evaluation"])

elif page == "Калькулятор":
    st.title("Калькулятор платежа")
    st.caption("Аннуитет · ежемесячный платёж · CZK · без комиссий и страхования")
    with st.form("calculator_form"):
        a, b, c = st.columns(3)
        amount = a.number_input("Сумма, CZK", min_value=1.0, value=120000.0)
        rate = b.number_input("Ставка, % годовых", min_value=0.0, max_value=100.0, value=12.0)
        months = c.number_input("Срок, мес.", min_value=1, max_value=600, value=24, step=1)
        calculate = st.form_submit_button("Рассчитать", type="primary")
    if calculate:
        result = call("POST", "/calculator/payment", json={"amount": amount, "annual_rate_pct": rate, "months": months})
        if result:
            a, b, c = st.columns(3)
            a.metric("В месяц", f"{result['monthly_payment']:,.2f} CZK")
            b.metric("Всего выплат", f"{result['total_payment']:,.2f} CZK")
            c.metric("Проценты", f"{result['interest']:,.2f} CZK")
            st.caption(result["assumption"])

elif page == "Журнал заявок":
    st.title("Журнал проверок")
    st.caption("Последние 30 сохранённых заявок с версиями правил и модели.")
    rows = call("GET", "/applications")
    if rows:
        table(rows)
        selected = st.selectbox("Открыть отчёт", rows, format_func=lambda r: f"{r['created_at'][:19]} · счёт {r['account_id']} · {STATUS[r['status']]}")
        saved = call("GET", f"/applications/{selected['application_id']}")
        if saved:
            result_view(saved["result"])
    else:
        st.info("Пока нет проверок. Создайте первую в разделе «Проверка заявки».")
