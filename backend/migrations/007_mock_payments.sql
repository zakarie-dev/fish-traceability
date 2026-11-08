CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    provider TEXT NOT NULL CHECK (provider IN ('EVC Plus', 'Zaad')),
    phone_number TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL,
    reference TEXT NOT NULL,
    transaction_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'Successful'
        CHECK (status IN ('Successful')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX payment_transactions_created_at_idx
    ON payment_transactions(created_at DESC);

ALTER TABLE payment_transactions ENABLE ROW LEVEL SECURITY;
