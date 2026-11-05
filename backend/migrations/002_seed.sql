-- Demo-only credentials. Replace these passwords and hashes before using this data outside a demo.
INSERT INTO landing_sites (id, name, region, gps_lat, gps_lng, is_active) VALUES
    ('10000000-0000-4000-8000-000000000001', 'Berbera', 'Somaliland', 10.4396, 45.0143, TRUE),
    ('10000000-0000-4000-8000-000000000002', 'Bosaso', 'Puntland', 11.2842, 49.1816, TRUE),
    ('10000000-0000-4000-8000-000000000003', 'Mogadishu', 'Banaadir', 2.0469, 45.3182, TRUE);

INSERT INTO users (id, email, hashed_password, role, assigned_site_id) VALUES
    ('20000000-0000-4000-8000-000000000001', 'admin@example.test', crypt('ChangeMe-Seed-Only-2026!', gen_salt('bf', 12)), 'Admin', NULL),
    ('20000000-0000-4000-8000-000000000002', 'officer.berbera@example.test', crypt('ChangeMe-Seed-Only-2026!', gen_salt('bf', 12)), 'Officer', '10000000-0000-4000-8000-000000000001'),
    ('20000000-0000-4000-8000-000000000003', 'officer.bosaso@example.test', crypt('ChangeMe-Seed-Only-2026!', gen_salt('bf', 12)), 'Officer', '10000000-0000-4000-8000-000000000002'),
    ('20000000-0000-4000-8000-000000000004', 'processor@example.test', crypt('ChangeMe-Seed-Only-2026!', gen_salt('bf', 12)), 'Processor', '10000000-0000-4000-8000-000000000001'),
    ('20000000-0000-4000-8000-000000000005', 'inspector@example.test', crypt('ChangeMe-Seed-Only-2026!', gen_salt('bf', 12)), 'Inspector', '10000000-0000-4000-8000-000000000003');

INSERT INTO species (id, name, is_protected) VALUES
    ('30000000-0000-4000-8000-000000000001', 'Yellowfin Tuna', FALSE),
    ('30000000-0000-4000-8000-000000000002', 'Kingfish', FALSE),
    ('30000000-0000-4000-8000-000000000003', 'Lobster', TRUE);

INSERT INTO vessels (
    id, name, reg_number, license_number, license_expiry,
    owner_name, owner_phone, home_port, length_m, engine_power, gear_type
) VALUES
    ('40000000-0000-4000-8000-000000000001', 'Al-Baraka', 'SOM-BRB-1042', 'LIC-BRB-2026-1042', DATE '2027-06-30',
     'Abdi Hassan', '+252 63 555 0101', 'Berbera', 18.50, 450, 'Longline'),
    ('40000000-0000-4000-8000-000000000002', 'Hilaac', 'SOM-BOS-2088', 'LIC-BOS-2026-2088', DATE '2027-09-15',
     'Amina Mohamed', '+252 90 555 0202', 'Bosaso', 14.20, 320, 'Gillnet');
