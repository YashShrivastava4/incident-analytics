"""
Cleans the raw incident event log CSV and loads it into Postgres as two tables:
raw_events (every event, cleaned) and incidents (one row per incident).

Usage:
    python src/clean_and_load.py --csv data/raw/incident_event_log.csv
    python src/clean_and_load.py --csv data/raw/incident_event_log.csv --no-load   (skip the DB write)

Needs DATABASE_URL_DIRECT set (env var or .env file) - the full-access role's
direct connection string, not the pooled one and not chatbot_readonly.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


EXPECTED_ROWS = 141_712
EXPECTED_INCIDENTS = 24_918

DATE_COLS = [
    "opened_at",
    "sys_created_at",
    "sys_updated_at",
    "resolved_at",
    "closed_at",
]
BOOLEAN_COLS = ["made_sla", "active", "knowledge", "u_priority_confirmation"]
COUNT_COLS = ["reassignment_count", "reopen_count", "sys_mod_count"]

# how each column collapses when we go from one row per event to one row per incident
LAST_ROW_COLS = [
    "incident_state",
    "made_sla",
    "closed_code",
    "resolved_at",
    "closed_at",
    "active",
    "priority",
]
FIRST_ROW_COLS = ["opened_at", "category"]
MAX_COLS = ["reassignment_count", "reopen_count", "sys_mod_count"]
PASSTHROUGH_LAST_COLS = [
    "subcategory",
    "impact",
    "urgency",
    "assignment_group",
    "assigned_to",
    "caller_id",
    "contact_type",
    "location",
]


def load_raw(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)

    n_rows = len(df)
    n_incidents = df["number"].nunique()
    print(
        f"Loaded {n_rows:,} rows / {n_incidents:,} distinct incidents from {csv_path}"
    )

    if n_rows != EXPECTED_ROWS or n_incidents != EXPECTED_INCIDENTS:
        raise ValueError(
            f"Got {n_rows:,} rows / {n_incidents:,} incidents, expected "
            f"{EXPECTED_ROWS:,} / {EXPECTED_INCIDENTS:,}. Wrong file or a bad download - check before continuing."
        )
    return df


def clean_events(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # "?" is how missing values are marked in this file, not a blank cell
    df = df.replace("?", pd.NA)

    # -100 is an undocumented incident_state that shows up mid-sequence on 2 incidents,
    # both of which still close out normally - see notes.md
    df["incident_state"] = df["incident_state"].replace("-100", "Unknown")

    # dates are DD/MM/YYYY in this file
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    truthy, falsy = {"true", "1", "yes"}, {"false", "0", "no"}
    for col in BOOLEAN_COLS:
        if col in df.columns:
            lowered = df[col].astype("string").str.strip().str.lower()
            df[col] = lowered.map(
                lambda v: True if v in truthy else (False if v in falsy else pd.NA)
            ).astype("boolean")

    for col in COUNT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    return df


def reduce_to_incidents(
    df: pd.DataFrame, expected_incidents: int | None = None
) -> pd.DataFrame:
    df = df.sort_values(["number", "sys_updated_at"])
    grouped = df.groupby("number", sort=False)

    last_rows = grouped[LAST_ROW_COLS + PASSTHROUGH_LAST_COLS].last()
    first_rows = grouped[FIRST_ROW_COLS].first()
    max_rows = grouped[MAX_COLS].max()

    incidents = last_rows.join(first_rows).join(max_rows).reset_index()

    if expected_incidents is not None and len(incidents) != expected_incidents:
        raise ValueError(
            f"Reduced to {len(incidents):,} incidents, expected {expected_incidents:,}."
        )

    return incidents


def compute_durations(incidents: pd.DataFrame) -> pd.DataFrame:
    incidents = incidents.copy()
    incidents["resolution_time_hours"] = (
        incidents["resolved_at"] - incidents["opened_at"]
    ).dt.total_seconds() / 3600
    incidents["time_to_close_hours"] = (
        incidents["closed_at"] - incidents["opened_at"]
    ).dt.total_seconds() / 3600
    # still-open incidents have no resolved_at/closed_at - leave these as NaN, don't fill or drop them
    return incidents


def get_engine(database_url: str | None = None):
    from sqlalchemy import create_engine

    url = database_url or os.environ.get("DATABASE_URL_DIRECT")
    if not url:
        raise RuntimeError(
            "DATABASE_URL_DIRECT is not set - add it to your .env or export it."
        )
    return create_engine(url)


def run_schema(engine, schema_path: Path) -> None:
    from sqlalchemy import text

    ddl = schema_path.read_text()
    with engine.begin() as conn:
        for statement in ddl.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    print(f"Schema applied from {schema_path}")


def load_to_postgres(
    engine, events_df: pd.DataFrame, incidents_df: pd.DataFrame
) -> None:
    events_df.to_sql(
        "raw_events", engine, if_exists="append", index=False, chunksize=5_000
    )
    print(f"Loaded {len(events_df):,} rows into raw_events")

    incidents_df.to_sql(
        "incidents", engine, if_exists="append", index=False, chunksize=5_000
    )
    print(f"Loaded {len(incidents_df):,} rows into incidents")


def main():
    parser = argparse.ArgumentParser(
        description="Clean the incident CSV and load it into Postgres"
    )
    parser.add_argument(
        "--csv", type=Path, required=True, help="path to the raw incident event log CSV"
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).parent.parent / "sql" / "schema.sql",
    )
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="clean and reduce only, don't write to Postgres",
    )
    args = parser.parse_args()

    raw = load_raw(args.csv)
    events = clean_events(raw)
    incidents = reduce_to_incidents(events, expected_incidents=EXPECTED_INCIDENTS)
    incidents = compute_durations(incidents)

    print(f"raw_events shape: {events.shape}")
    print(f"incidents shape:  {incidents.shape}")
    print(f"incidents with no resolved_at: {incidents['resolved_at'].isna().sum():,}")

    if args.no_load:
        print("--no-load set, skipping the Postgres write.")
        return

    engine = get_engine()
    run_schema(engine, args.schema)
    load_to_postgres(engine, events, incidents)


if __name__ == "__main__":
    sys.exit(main())
