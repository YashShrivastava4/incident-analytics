-- run against Neon using the DIRECT connection string, as your own full-access role
-- read-only role for the chatbot connection
CREATE ROLE chatbot_readonly WITH LOGIN PASSWORD 'Your_Password';
-- pick your own password, put the same one in .env / secrets.toml
GRANT CONNECT ON DATABASE neondb TO chatbot_readonly;
GRANT USAGE ON SCHEMA public TO chatbot_readonly;
GRANT SELECT ON incidents TO chatbot_readonly;
GRANT SELECT ON v_sla_by_priority TO chatbot_readonly;
GRANT SELECT ON v_sla_by_category TO chatbot_readonly;
GRANT SELECT ON v_resolution_time TO chatbot_readonly;
GRANT SELECT ON v_volume_trend TO chatbot_readonly;
GRANT SELECT ON v_reassignment_distribution TO chatbot_readonly;
GRANT SELECT ON v_assignment_group_summary TO chatbot_readonly;