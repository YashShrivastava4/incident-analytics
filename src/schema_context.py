"""
Builds the schema description injected into every Groq prompt.

Introspects information_schema live instead of hardcoding the column list,
so it's self-correcting if a column gets added or renamed later. Anything
the live query returns that isn't in SEMANTIC_DESCRIPTIONS below just gets
a generic fallback line instead of being silently skipped.
"""
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger("schema_context")

TABLE_NAME = "incidents"
VIEW_NAMES = [
    "v_sla_by_priority",
    "v_sla_by_category",
    "v_resolution_time",
    "v_volume_trend",
    "v_reassignment_distribution",
    "v_assignment_group_summary",
]

# superset of every column this project's tables/views could contain, keyed
# lowercase. introspection below only keeps the ones actually in the live DB.
SEMANTIC_DESCRIPTIONS = {
    "number": "unique incident identifier, e.g. INC0012345",
    "incident_state": "current lifecycle state (New, Active, Resolved, Closed, etc.)",
    "active": "boolean, true if the incident is still open",
    "reassignment_count": "how many times the incident was reassigned, final value",
    "reopen_count": "how many times the incident was reopened, final value",
    "sys_mod_count": "total number of update events logged for this incident",
    "made_sla": "boolean, true if the incident was resolved within its target SLA",
    "opened_at": "timestamp the incident was first opened",
    "sys_created_at": "timestamp the underlying record was first created",
    "sys_updated_at": "timestamp of the incident's last update",
    "resolved_at": "timestamp the incident was resolved, null if still open",
    "closed_at": "timestamp the incident was closed, null if not closed",
    "contact_type": "how the incident was reported (phone, self-service, email, etc.)",
    "location": "site/location the incident was reported from, anonymized",
    "category": "top-level incident category, assigned at open time",
    "subcategory": "more specific category under the top-level category",
    "u_symptom": "reported symptom description, anonymized/categorical",
    "cmdb_ci": "configuration item affected, anonymized (mostly missing in this dataset)",
    "impact": "business impact level, formatted like '1 - High'",
    "urgency": "urgency level, formatted like '1 - High'",
    "priority": "priority at closure, formatted like '1 - Critical'; drives SLA target",
    "assignment_group": "anonymized support team the incident was assigned to, e.g. 'Group 24'",
    "assigned_to": "anonymized individual assignee, e.g. 'Resolver 123'",
    "caller_id": "anonymized reporter identity, e.g. 'Caller 2403'",
    "closed_code": "resolution code recorded at closure",
    "resolved_by": "anonymized identity of who resolved the incident",
    "resolution_time_hours": "resolved_at minus opened_at in hours, null if unresolved; raw calendar time, not business hours",
    "time_to_close_hours": "closed_at minus opened_at in hours, null if not closed; raw calendar time, not business hours",
    "grain": "'day' | 'week' | 'month', which time bucket a v_volume_trend row aggregates",
    "period": "the date for this grain's bucket, e.g. a specific day/week-start/month-start",
    "incident_count": "number of incidents in this group",
    "sla_compliance_rate": "share of incidents in the group where made_sla was true",
    "sla_breach_rate": "share of incidents in the group where made_sla was false",
    "avg_resolution_hours": "mean resolution_time_hours for the group",
    "median_resolution_hours": "median resolution_time_hours for the group, via percentile_cont",
    "volume_rank": "assignment group's rank by incident_count, 1 = highest volume",
}

FEW_SHOT_EXAMPLES = [
    {
        "question": "What's the SLA compliance rate for Critical priority incidents?",
        "sql": (
            "SELECT priority, sla_compliance_rate FROM v_sla_by_priority "
            "WHERE priority = '1 - Critical'"
        ),
    },
    {
        "question": "How many incidents were opened per month in 2016?",
        "sql": (
            "SELECT * FROM v_volume_trend WHERE grain = 'month' "
            "AND period >= '2016-01-01' AND period < '2017-01-01' "
            "ORDER BY period"
        ),
    },
    {
        "question": "Which assignment group handles the most incidents?",
        "sql": (
            "SELECT assignment_group, incident_count FROM v_assignment_group_summary "
            "ORDER BY incident_count DESC LIMIT 5"
        ),
    },
    {
        "question": "What's the average and median resolution time for High priority Network incidents?",
        "sql": (
            "SELECT avg_resolution_hours, median_resolution_hours FROM v_resolution_time "
            "WHERE priority = '2 - High' AND category = 'Network'"
        ),
    },
    {
        "question": "How many incidents have never been reassigned?",
        "sql": "SELECT COUNT(*) FROM incidents WHERE reassignment_count = 0",
    },
]

# view output column names above (sla_compliance_rate, avg_resolution_hours,
# median_resolution_hours, incident_count, period, grain, volume_rank) are
# confirmed against the real sql/views.sql, not guessed.


def _introspect_columns(engine, table_name):
    query = text(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = :table_name
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"table_name": table_name}).fetchall()
    return [(r[0], r[1]) for r in rows]


def _describe_columns(columns):
    lines = []
    for name, dtype in columns:
        desc = SEMANTIC_DESCRIPTIONS.get(name.lower())
        if desc:
            lines.append(f"  - {name} ({dtype}): {desc}")
        else:
            lines.append(f"  - {name} ({dtype}): [no description on file, verify usage]")
            logger.info("no semantic description for column '%s', add one to SEMANTIC_DESCRIPTIONS", name)
    return "\n".join(lines)


def build_schema_context(database_url: str) -> str:
    """
    Connects with the given (read-only) connection string, introspects
    incidents + the six KPI views, and returns the text block to inject
    into the Groq prompt. Call once per app session and cache the result,
    the schema doesn't change between questions.
    """
    engine = create_engine(database_url)
    blocks = []

    incident_cols = _introspect_columns(engine, TABLE_NAME)
    if not incident_cols:
        logger.warning("no columns found for table '%s', check connection/permissions", TABLE_NAME)
    blocks.append(f"TABLE incidents (one row per incident):\n{_describe_columns(incident_cols)}")

    for view_name in VIEW_NAMES:
        view_cols = _introspect_columns(engine, view_name)
        if not view_cols:
            logger.warning("no columns found for view '%s', check connection/permissions", view_name)
            continue
        blocks.append(f"VIEW {view_name}:\n{_describe_columns(view_cols)}")

    schema_block = "\n\n".join(blocks)

    examples_block = "\n\n".join(
        f"Q: {ex['question']}\nSQL: {ex['sql']}" for ex in FEW_SHOT_EXAMPLES
    )

    return (
        "You are a Postgres SQL generator for an IT incident analytics database.\n\n"
        f"{schema_block}\n\n"
        "Only use the tables/views and columns listed above. Never invent a column name.\n\n"
        "EXAMPLES:\n"
        f"{examples_block}"
    )
