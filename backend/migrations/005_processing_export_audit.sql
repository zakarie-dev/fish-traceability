ALTER TABLE users
    DROP CONSTRAINT users_role_check;

ALTER TABLE users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('Admin', 'Officer', 'Processor', 'Inspector', 'Exporter'));

ALTER TABLE inspections
    ADD COLUMN inspected_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX inspections_lot_inspected_at_idx
    ON inspections(lot_id, inspected_at DESC);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_log_created_at_idx ON audit_log(created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
