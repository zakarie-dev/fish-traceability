ALTER TABLE lots
    ALTER COLUMN catch_id DROP NOT NULL;

ALTER TABLE consignments
    ADD COLUMN status TEXT NOT NULL DEFAULT 'Active'
    CHECK (status IN ('Active', 'Recalled'));

CREATE TABLE lot_split_losses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    loss_weight NUMERIC(10, 2) NOT NULL CHECK (loss_weight > 0),
    loss_reason TEXT
);

CREATE INDEX lot_split_losses_parent_lot_id_idx
    ON lot_split_losses(parent_lot_id);

CREATE TABLE sms_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Sent', 'Failed'))
);

ALTER TABLE lot_split_losses ENABLE ROW LEVEL SECURITY;
ALTER TABLE sms_outbox ENABLE ROW LEVEL SECURITY;
