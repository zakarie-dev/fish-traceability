ALTER TABLE temperature_logs
    ADD COLUMN temperature_type TEXT NOT NULL DEFAULT 'Chilled'
    CHECK (temperature_type IN ('Chilled', 'Frozen'));
