-- Run this against your Neon database using the DIRECT connection string,
-- logged in as your own full-access role (the one Neon gives you by default).

-- ---------------------------------------------------------------------
-- Part 1: run now (Phase 0), before any tables exist.
-- ---------------------------------------------------------------------

-- Dedicated read-only role for the chatbot connection.
-- Pick your own password here and put the SAME one in .env / secrets.toml
-- under DATABASE_URL_POOLED / DATABASE_URL.
CREATE ROLE chatbot_readonly WITH LOGIN PASSWORD 'replace-with-a-real-password';

-- Postgres default is CONNECT-only for new roles; this is just explicit.
GRANT CONNECT ON DATABASE neondb TO chatbot_readonly;
-- ^ replace "neondb" with your actual database name if Neon named it differently.

-- ---------------------------------------------------------------------
-- Part 2: run AFTER Phase 2 (raw_events, incidents tables exist) and
-- AFTER Phase 3 (KPI views exist). Do not run this section yet.
-- ---------------------------------------------------------------------

-- GRANT USAGE ON SCHEMA public TO chatbot_readonly;
-- GRANT SELECT ON incidents TO chatbot_readonly;
-- GRANT SELECT ON v_sla_by_priority TO chatbot_readonly;
-- GRANT SELECT ON v_sla_by_category TO chatbot_readonly;
-- GRANT SELECT ON v_resolution_time TO chatbot_readonly;
-- GRANT SELECT ON v_volume_trend TO chatbot_readonly;
-- GRANT SELECT ON v_reassignment_distribution TO chatbot_readonly;
-- GRANT SELECT ON v_assignment_group_summary TO chatbot_readonly;
--
-- Deliberately NOT granting SELECT on raw_events — the chatbot has no
-- business reading the untouched event log, only the reduced table + views.

-- ---------------------------------------------------------------------
-- Verification (run anytime after Part 2, as a sanity check):
-- Connect as chatbot_readonly (e.g. via psql using its own connection
-- string) and confirm this FAILS with a permissions error, not silently
-- returning a row count of 0 or succeeding:
--
--   DELETE FROM incidents;
--
-- If it fails with "permission denied for table incidents", Layer 1 of
-- the guardrail (Phase 7) is confirmed working at the database level.
-- ---------------------------------------------------------------------
