CREATE SCHEMA raw;
CREATE SCHEMA clean;
CREATE SCHEMA analytics;

CREATE TABLE raw.dataset (
    id integer PRIMARY KEY CHECK (id = 1),
    mode text NOT NULL CHECK (mode IN ('demo', 'berka')),
    reference_date date NOT NULL,
    manifest jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE clean.clients (
    client_id integer PRIMARY KEY,
    district_id integer NOT NULL
);
CREATE TABLE clean.accounts (
    account_id integer PRIMARY KEY,
    client_id integer NOT NULL REFERENCES clean.clients,
    district_id integer NOT NULL,
    opened_at date NOT NULL
);
CREATE TABLE clean.transactions (
    trans_id bigint PRIMARY KEY,
    account_id integer NOT NULL REFERENCES clean.accounts,
    booked_at date NOT NULL,
    direction text NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount numeric(14,2) NOT NULL CHECK (amount >= 0),
    balance numeric(14,2) NOT NULL,
    category text NOT NULL DEFAULT ''
);
CREATE INDEX ix_transactions_account_date ON clean.transactions(account_id, booked_at);
CREATE TABLE clean.loans (
    loan_id integer PRIMARY KEY,
    account_id integer UNIQUE NOT NULL REFERENCES clean.accounts,
    issued_at date NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    months integer NOT NULL CHECK (months > 0),
    payment numeric(14,2) NOT NULL CHECK (payment > 0),
    status char(1) NOT NULL CHECK (status IN ('A', 'B', 'C', 'D'))
);
CREATE TABLE clean.applications (
    application_id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    account_id integer NOT NULL REFERENCES clean.accounts,
    dataset_mode text NOT NULL,
    request jsonb NOT NULL,
    result jsonb NOT NULL
);

-- Used both for historical training examples and API application scoring.
-- The scoring day itself is excluded: daily data do not provide an intraday order.
CREATE FUNCTION analytics.account_features(
    p_account integer, p_as_of date, p_amount double precision,
    p_months integer, p_payment double precision
) RETURNS TABLE (
    account_age_days double precision, amount double precision,
    months double precision, payment double precision,
    tx_count_90d double precision, mean_balance_90d double precision,
    min_balance_90d double precision, negative_share_90d double precision,
    monthly_inflow_90d double precision, payment_to_inflow double precision
) LANGUAGE SQL STABLE AS $$
    SELECT (p_as_of - a.opened_at)::double precision,
           p_amount, p_months::double precision, p_payment,
           s.n::double precision, s.avg_balance, s.min_balance,
           s.negative_share, s.inflow / 3.0,
           p_payment / NULLIF(s.inflow / 3.0, 0)
    FROM clean.accounts a
    CROSS JOIN LATERAL (
        SELECT count(*) AS n,
               avg(t.balance)::double precision AS avg_balance,
               min(t.balance)::double precision AS min_balance,
               avg((t.balance < 0)::int)::double precision AS negative_share,
               COALESCE(sum(t.amount) FILTER (
                   WHERE t.direction = 'credit' AND t.category <> 'UROK'), 0)::double precision AS inflow
        FROM clean.transactions t
        WHERE t.account_id = a.account_id
          AND t.booked_at >= p_as_of - 90 AND t.booked_at < p_as_of
    ) s
    WHERE a.account_id = p_account AND a.opened_at <= p_as_of;
$$;

CREATE VIEW analytics.training_mart AS
SELECT l.loan_id, l.account_id, l.issued_at,
       (l.issued_at + make_interval(months => l.months))::date AS scheduled_end,
       (l.status = 'B')::integer AS target, f.*
FROM clean.loans l
CROSS JOIN LATERAL analytics.account_features(
    l.account_id, l.issued_at, l.amount::double precision, l.months, l.payment::double precision
) f
WHERE l.status IN ('A', 'B');
