"""
Fixed-SQL dashboard metrics for the sidebar overview and trend chart.

Deliberately separate from the NL-to-SQL path: these queries are written by us,
not generated from user input, so they never touch generate_sql or the
guardrail — there's nothing to validate because the SQL isn't coming from an
LLM. Reuses execute_query() so there's still only one code path that opens a
connection to chatbot_readonly.
"""
import logging
import pandas as pd

from src.query_executor import execute_query

logger = logging.getLogger("dashboard_metrics")

# one round trip for all five headline numbers
OVERVIEW_QUERY = """
SELECT
    COUNT(*) AS total_incidents,
    MIN(opened_at)::date AS earliest_opened,
    MAX(opened_at)::date AS latest_opened,
    AVG(made_sla::int) AS sla_compliance_rate,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_time_hours)
        FILTER (WHERE resolution_time_hours IS NOT NULL) AS median_resolution_hours
FROM incidents
"""

# not read from v_resolution_time on purpose: that view is grouped by
# priority + category, so there's no ungrouped overall row, and a median
# can't be recombined from group medians the way an average can. Same
# percentile_cont logic as the view, just applied without the GROUP BY.
MONTHLY_TREND_QUERY = """
SELECT period, incident_count
FROM v_volume_trend
WHERE grain = 'month'
ORDER BY period
"""


def get_overview_metrics(database_url: str) -> dict:
    """Returns {} if the query fails, so callers can render a graceful fallback."""
    success, df, error = execute_query(OVERVIEW_QUERY, database_url)
    if not success or df is None or df.empty:
        logger.warning("overview metrics query failed: %s", error)
        return {}

    row = df.iloc[0]
    sla = row["sla_compliance_rate"]
    median = row["median_resolution_hours"]
    return {
        "total_incidents": int(row["total_incidents"]),
        "earliest_opened": row["earliest_opened"],
        "latest_opened": row["latest_opened"],
        "sla_compliance_rate": float(sla) if pd.notna(sla) else None,
        "median_resolution_hours": float(median) if pd.notna(median) else None,
    }


def get_monthly_trend(database_url: str) -> pd.DataFrame:
    """Empty frame (not None) on failure, so callers can skip the chart cleanly."""
    success, df, error = execute_query(MONTHLY_TREND_QUERY, database_url)
    if not success or df is None:
        logger.warning("monthly trend query failed: %s", error)
        return pd.DataFrame(columns=["period", "incident_count"])
    return df
