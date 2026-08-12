"""
Validates the cleaning/reduction outcome directly against the live
incidents table, rather than unit-testing clean_and_load.py's internal
functions - keeps this test honest about the real data instead of the
function signatures. Skipped unless a DB connection is provided.
"""
import os
import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL_POOLED")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL_POOLED not set, cannot check the live table",
)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL)
    yield eng
    eng.dispose()


def test_incident_level_row_count(engine):
    # the whole point of the reduction: one row per incident, not one per event
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM incidents")).scalar()
    assert count == 24918, f"expected 24918 incidents, got {count}"


def test_no_question_mark_sentinel_remains(engine):
    with engine.connect() as conn:
        columns = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'incidents' AND data_type IN ('text', 'character varying')"
            )
        ).fetchall()
        for (column_name,) in columns:
            count = conn.execute(
                text(f'SELECT COUNT(*) FROM incidents WHERE "{column_name}" = :sentinel'),
                {"sentinel": "?"},
            ).scalar()
            assert count == 0, f"column '{column_name}' still has literal '?' sentinel values"


def test_duration_columns_non_negative(engine):
    with engine.connect() as conn:
        bad_resolution = conn.execute(
            text("SELECT COUNT(*) FROM incidents WHERE resolution_time_hours < 0")
        ).scalar()
        bad_close = conn.execute(
            text("SELECT COUNT(*) FROM incidents WHERE time_to_close_hours < 0")
        ).scalar()
    assert bad_resolution == 0, f"{bad_resolution} rows have negative resolution_time_hours"
    assert bad_close == 0, f"{bad_close} rows have negative time_to_close_hours"


def test_resolution_time_null_only_when_unresolved(engine):
    with engine.connect() as conn:
        mismatched = conn.execute(
            text(
                "SELECT COUNT(*) FROM incidents "
                "WHERE resolved_at IS NOT NULL AND resolution_time_hours IS NULL"
            )
        ).scalar()
    assert mismatched == 0, f"{mismatched} resolved incidents have a null resolution_time_hours"
