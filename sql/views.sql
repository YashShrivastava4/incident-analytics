-- SLA compliance rate by priority
CREATE OR REPLACE VIEW v_sla_by_priority AS
SELECT priority,
    COUNT(*) AS incident_count,
    AVG(made_sla::int) AS sla_compliance_rate
FROM incidents
GROUP BY priority
ORDER BY priority;
-- SLA compliance rate by category
CREATE OR REPLACE VIEW v_sla_by_category AS
SELECT category,
    COUNT(*) AS incident_count,
    AVG(made_sla::int) AS sla_compliance_rate
FROM incidents
GROUP BY category
ORDER BY category;
-- avg and median resolution time, broken down by priority and category together
CREATE OR REPLACE VIEW v_resolution_time AS
SELECT priority,
    category,
    COUNT(*) AS incident_count,
    AVG(resolution_time_hours) AS avg_resolution_hours,
    percentile_cont(0.5) WITHIN GROUP (
        ORDER BY resolution_time_hours
    ) AS median_resolution_hours
FROM incidents
WHERE resolution_time_hours IS NOT NULL
GROUP BY priority,
    category
ORDER BY priority,
    category;
-- incident volume by day, week, and month, all in one view via a grain column
CREATE OR REPLACE VIEW v_volume_trend AS
SELECT 'day' AS grain,
    opened_at::date AS period,
    COUNT(*) AS incident_count
FROM incidents
WHERE opened_at IS NOT NULL
GROUP BY opened_at::date
UNION ALL
SELECT 'week' AS grain,
    date_trunc('week', opened_at)::date AS period,
    COUNT(*) AS incident_count
FROM incidents
WHERE opened_at IS NOT NULL
GROUP BY date_trunc('week', opened_at)
UNION ALL
SELECT 'month' AS grain,
    date_trunc('month', opened_at)::date AS period,
    COUNT(*) AS incident_count
FROM incidents
WHERE opened_at IS NOT NULL
GROUP BY date_trunc('month', opened_at)
ORDER BY grain,
    period;
-- reassignment count histogram, used as a proxy for handling efficiency
CREATE OR REPLACE VIEW v_reassignment_distribution AS
SELECT reassignment_count,
    COUNT(*) AS incident_count
FROM incidents
WHERE reassignment_count IS NOT NULL
GROUP BY reassignment_count
ORDER BY reassignment_count;
-- volume and SLA-breach rate per assignment group, ranked by volume
CREATE OR REPLACE VIEW v_assignment_group_summary AS
SELECT assignment_group,
    COUNT(*) AS incident_count,
    AVG(
        CASE
            WHEN made_sla THEN 0
            ELSE 1
        END
    ) AS sla_breach_rate,
    RANK() OVER (
        ORDER BY COUNT(*) DESC
    ) AS volume_rank
FROM incidents
GROUP BY assignment_group
ORDER BY volume_rank;