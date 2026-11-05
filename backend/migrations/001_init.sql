CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE landing_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL,
    gps_lat NUMERIC(9, 6) CHECK (gps_lat BETWEEN -90 AND 90),
    gps_lng NUMERIC(9, 6) CHECK (gps_lng BETWEEN -180 AND 180),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Admin', 'Officer', 'Processor', 'Inspector', 'Exporter')),
    assigned_site_id UUID REFERENCES landing_sites(id) ON DELETE SET NULL
);

CREATE TABLE vessels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    reg_number TEXT NOT NULL UNIQUE,
    license_number TEXT NOT NULL UNIQUE,
    license_expiry DATE NOT NULL,
    owner_name TEXT NOT NULL,
    owner_phone TEXT,
    home_port TEXT NOT NULL,
    length_m NUMERIC(6, 2) CHECK (length_m > 0),
    engine_power INTEGER CHECK (engine_power > 0),
    gear_type TEXT NOT NULL
);

CREATE TABLE species (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE catches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vessel_id UUID NOT NULL REFERENCES vessels(id) ON DELETE RESTRICT,
    officer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    landing_site_id UUID NOT NULL REFERENCES landing_sites(id) ON DELETE RESTRICT,
    catch_date DATE NOT NULL,
    landing_date DATE NOT NULL,
    catch_area TEXT NOT NULL,
    gear_used TEXT NOT NULL,
    first_temp NUMERIC(5, 2),
    CHECK (landing_date >= catch_date)
);

CREATE TABLE lots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_code TEXT NOT NULL UNIQUE,
    catch_id UUID NOT NULL REFERENCES catches(id) ON DELETE RESTRICT,
    species_id UUID NOT NULL REFERENCES species(id) ON DELETE RESTRICT,
    current_weight NUMERIC(10, 2) NOT NULL CHECK (current_weight >= 0),
    status TEXT NOT NULL CHECK (status IN ('Available', 'Split', 'Merged', 'Processed', 'Recalled')),
    parent_lot_id UUID REFERENCES lots(id) ON DELETE SET NULL,
    CHECK (parent_lot_id IS NULL OR parent_lot_id <> id)
);

CREATE TABLE lot_links (
    parent_lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    child_lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    PRIMARY KEY (parent_lot_id, child_lot_id),
    CHECK (parent_lot_id <> child_lot_id)
);

CREATE TABLE processing_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    step_type TEXT NOT NULL,
    operator_id UUID REFERENCES users(id) ON DELETE SET NULL,
    weight_in NUMERIC(10, 2) NOT NULL CHECK (weight_in >= 0),
    weight_out NUMERIC(10, 2) NOT NULL CHECK (weight_out >= 0),
    yield_pct NUMERIC(5, 2) CHECK (yield_pct BETWEEN 0 AND 100),
    CHECK (weight_out <= weight_in)
);

CREATE TABLE temperature_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    temp_celsius NUMERIC(5, 2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location TEXT NOT NULL,
    is_breach BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    inspector_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    grade TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    notes TEXT,
    photo_url TEXT
);

CREATE TABLE consignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buyer_name TEXT NOT NULL,
    destination_country TEXT NOT NULL,
    shipping_date DATE NOT NULL,
    container_number TEXT NOT NULL,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE consignment_lots (
    consignment_id UUID NOT NULL REFERENCES consignments(id) ON DELETE CASCADE,
    lot_id UUID NOT NULL REFERENCES lots(id) ON DELETE RESTRICT,
    PRIMARY KEY (consignment_id, lot_id)
);

CREATE TABLE certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consignment_id UUID NOT NULL REFERENCES consignments(id) ON DELETE CASCADE,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX catches_vessel_id_idx ON catches(vessel_id);
CREATE INDEX catches_officer_id_idx ON catches(officer_id);
CREATE INDEX catches_landing_site_id_idx ON catches(landing_site_id);
CREATE INDEX lots_catch_id_idx ON lots(catch_id);
CREATE INDEX lots_species_id_idx ON lots(species_id);
CREATE INDEX lots_parent_lot_id_idx ON lots(parent_lot_id);
CREATE INDEX lot_links_child_lot_id_idx ON lot_links(child_lot_id);
CREATE INDEX processing_steps_lot_id_idx ON processing_steps(lot_id);
CREATE INDEX temperature_logs_lot_recorded_idx ON temperature_logs(lot_id, recorded_at DESC);
CREATE INDEX inspections_lot_id_idx ON inspections(lot_id);
CREATE INDEX consignment_lots_lot_id_idx ON consignment_lots(lot_id);
CREATE INDEX certificates_consignment_id_idx ON certificates(consignment_id);

ALTER TABLE landing_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE vessels ENABLE ROW LEVEL SECURITY;
ALTER TABLE species ENABLE ROW LEVEL SECURITY;
ALTER TABLE catches ENABLE ROW LEVEL SECURITY;
ALTER TABLE lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE lot_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE temperature_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspections ENABLE ROW LEVEL SECURITY;
ALTER TABLE consignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE consignment_lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE certificates ENABLE ROW LEVEL SECURITY;
