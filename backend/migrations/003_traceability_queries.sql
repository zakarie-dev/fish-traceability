-- Supabase SQL Editor does not automatically supply positional bind parameters.
-- Replace each example value below with a real value, then run that query.

-- 1. Backward trace by lot code.
-- Finds every original catch and vessel on this lot and any ancestor lots.
WITH RECURSIVE
input AS (
    SELECT 'LOT-BER-20261029-001'::TEXT AS lot_code
),
ancestors AS (
    SELECT l.id, ARRAY[l.id] AS path
    FROM lots AS l
    CROSS JOIN input AS i
    WHERE l.lot_code = i.lot_code

    UNION ALL

    SELECT parent.id, a.path || parent.id
    FROM ancestors AS a
    JOIN lot_links AS edge ON edge.child_lot_id = a.id
    JOIN lots AS parent ON parent.id = edge.parent_lot_id
    WHERE NOT parent.id = ANY(a.path)
)
SELECT DISTINCT l.catch_id, c.vessel_id
FROM ancestors AS a
JOIN lots AS l ON l.id = a.id
JOIN catches AS c ON c.id = l.catch_id
ORDER BY l.catch_id, c.vessel_id;

-- 2. Forward recall trace by catch ID.
-- Finds every consignment containing a lot from the catch or any descendant.
WITH RECURSIVE
input AS (
    SELECT '00000000-0000-0000-0000-000000000000'::UUID AS catch_id
),
descendants AS (
    SELECT l.id, ARRAY[l.id] AS path
    FROM lots AS l
    CROSS JOIN input AS i
    WHERE l.catch_id = i.catch_id

    UNION ALL

    SELECT child.id, d.path || child.id
    FROM descendants AS d
    JOIN lot_links AS edge ON edge.parent_lot_id = d.id
    JOIN lots AS child ON child.id = edge.child_lot_id
    WHERE NOT child.id = ANY(d.path)
)
SELECT DISTINCT cl.consignment_id
FROM descendants AS d
JOIN consignment_lots AS cl ON cl.lot_id = d.id
ORDER BY cl.consignment_id;

-- 2b. Forward recall trace starting from one original lot ID instead.
WITH RECURSIVE
input AS (
    SELECT '00000000-0000-0000-0000-000000000000'::UUID AS lot_id
),
descendants AS (
    SELECT l.id, ARRAY[l.id] AS path
    FROM lots AS l
    CROSS JOIN input AS i
    WHERE l.id = i.lot_id

    UNION ALL

    SELECT child.id, d.path || child.id
    FROM descendants AS d
    JOIN lot_links AS edge ON edge.parent_lot_id = d.id
    JOIN lots AS child ON child.id = edge.child_lot_id
    WHERE NOT child.id = ANY(d.path)
)
SELECT DISTINCT cl.consignment_id
FROM descendants AS d
JOIN consignment_lots AS cl ON cl.lot_id = d.id
ORDER BY cl.consignment_id;

-- 3. Weight conservation for one parent lot.
-- Replace the example UUID. Processing loss is computed from processing steps
-- recorded against this parent lot.
WITH
input AS (
    SELECT '00000000-0000-0000-0000-000000000000'::UUID AS lot_id
),
child_weights AS (
    SELECT COALESCE(SUM(child.current_weight), 0)::NUMERIC(10, 2) AS child_weight
    FROM lot_links AS edge
    JOIN lots AS child ON child.id = edge.child_lot_id
    CROSS JOIN input AS i
    WHERE edge.parent_lot_id = i.lot_id
),
processing_loss AS (
    SELECT COALESCE(SUM(step.weight_in - step.weight_out), 0)::NUMERIC(10, 2) AS loss_weight
    FROM processing_steps AS step
    CROSS JOIN input AS i
    WHERE step.lot_id = i.lot_id
),
parent_weight AS (
    SELECT l.current_weight
    FROM lots AS l
    CROSS JOIN input AS i
    WHERE l.id = i.lot_id
)
SELECT
    parent_weight.current_weight AS parent_weight,
    child_weights.child_weight,
    processing_loss.loss_weight,
    child_weights.child_weight + processing_loss.loss_weight AS accounted_weight,
    child_weights.child_weight + processing_loss.loss_weight = parent_weight.current_weight AS is_conserved
FROM parent_weight
CROSS JOIN child_weights
CROSS JOIN processing_loss;
