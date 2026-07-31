-- raw event log, one row per event, kept as-is for reference/debugging
CREATE TABLE IF NOT EXISTS raw_events (
    event_id                    SERIAL PRIMARY KEY,
    number                      VARCHAR(20) NOT NULL,
    incident_state              VARCHAR(30),
    active                      BOOLEAN,
    reassignment_count          INTEGER,
    reopen_count                INTEGER,
    sys_mod_count               INTEGER,
    made_sla                    BOOLEAN,
    caller_id                   VARCHAR(50),
    opened_by                   VARCHAR(50),
    opened_at                   TIMESTAMP,
    sys_created_by              VARCHAR(50),
    sys_created_at              TIMESTAMP,
    sys_updated_by              VARCHAR(50),
    sys_updated_at              TIMESTAMP,
    contact_type                VARCHAR(50),
    location                    VARCHAR(50),
    category                    VARCHAR(50),
    subcategory                 VARCHAR(100),
    u_symptom                   VARCHAR(100),
    cmdb_ci                     VARCHAR(50),
    impact                      VARCHAR(20),
    urgency                     VARCHAR(20),
    priority                    VARCHAR(20),
    assignment_group            VARCHAR(50),
    assigned_to                 VARCHAR(50),
    knowledge                   BOOLEAN,
    u_priority_confirmation     BOOLEAN,
    notify                      VARCHAR(30),
    problem_id                  VARCHAR(50),
    rfc                         VARCHAR(20),
    vendor                      VARCHAR(50),
    caused_by                   VARCHAR(50),
    closed_code                 VARCHAR(20),
    resolved_by                 VARCHAR(50),
    resolved_at                 TIMESTAMP,
    closed_at                   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_raw_events_number ON raw_events(number);

-- one row per incident, this is what Power BI and the chatbot actually query
CREATE TABLE IF NOT EXISTS incidents (
    number                      VARCHAR(20) PRIMARY KEY,
    incident_state              VARCHAR(30),
    active                      BOOLEAN,
    made_sla                    BOOLEAN,
    closed_code                 VARCHAR(20),
    opened_at                   TIMESTAMP,
    resolved_at                 TIMESTAMP,
    closed_at                   TIMESTAMP,
    resolution_time_hours       NUMERIC,
    time_to_close_hours         NUMERIC,
    category                    VARCHAR(50),
    subcategory                 VARCHAR(100),
    priority                    VARCHAR(20),
    impact                      VARCHAR(20),
    urgency                     VARCHAR(20),
    assignment_group            VARCHAR(50),
    assigned_to                 VARCHAR(50),
    caller_id                   VARCHAR(50),
    contact_type                VARCHAR(50),
    location                    VARCHAR(50),
    reassignment_count          INTEGER,
    reopen_count                INTEGER,
    sys_mod_count               INTEGER
);

CREATE INDEX IF NOT EXISTS idx_incidents_priority ON incidents(priority);
CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);
CREATE INDEX IF NOT EXISTS idx_incidents_assignment_group ON incidents(assignment_group);
