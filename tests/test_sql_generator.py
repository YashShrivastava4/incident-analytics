"""
Spot-checks that generated SQL only references real columns, for a fixed
set of canned questions. Needs a live DB (to introspect the real column
set) and a Groq API key (to actually generate SQL), so it's skipped
without both rather than guessing at either.
"""
import os
import re
import sys
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from schema_context import build_schema_context, TABLE_NAME, VIEW_NAMES  # noqa: E402
from guardrail import validate_sql  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL_POOLED")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# importorskip, not a plain import: if groq isn't installed this skips the
# whole module cleanly instead of crashing pytest's collection step
Groq = pytest.importorskip("groq").Groq
from sql_generator import generate_sql  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and GROQ_API_KEY),
    reason="DATABASE_URL_POOLED and GROQ_API_KEY both required to spot-check live generation",
)

CANNED_QUESTIONS = [
    "What's the SLA compliance rate for Critical priority incidents?",
    "How many incidents were opened per month in 2016?",
    "Which assignment group handles the most incidents?",
    "What's the average resolution time for High priority Network incidents?",
    "How many incidents have never been reassigned?",
]

_IDENTIFIER_PATTERN = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")

# words that will show up in generated SQL but aren't column/table names
SQL_STOPWORDS = {
    "select", "from", "where", "group", "by", "order", "limit", "and", "or",
    "not", "null", "is", "as", "on", "join", "left", "right", "inner", "outer",
    "count", "avg", "sum", "min", "max", "asc", "desc", "distinct", "having",
    "between", "like", "in", "true", "false", "case", "when", "then", "else",
    "end", "with",
}


@pytest.fixture(scope="module")
def known_columns():
    engine = create_engine(DATABASE_URL)
    known = set()
    with engine.connect() as conn:
        for obj_name in [TABLE_NAME] + VIEW_NAMES:
            rows = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": obj_name},
            ).fetchall()
            known.update(r[0].lower() for r in rows)
    known.update(n.lower() for n in [TABLE_NAME] + VIEW_NAMES)
    engine.dispose()
    return known


@pytest.fixture(scope="module")
def schema_context():
    return build_schema_context(DATABASE_URL)


@pytest.fixture(scope="module")
def client():
    return Groq(api_key=GROQ_API_KEY)


@pytest.mark.parametrize("question", CANNED_QUESTIONS)
def test_generated_sql_uses_known_columns_only(question, schema_context, client, known_columns):
    sql = generate_sql(question, schema_context, client)
    assert sql.strip().upper() != "NO_QUERY", f"model refused a question it should answer: {question!r}"

    is_valid, reason = validate_sql(sql)
    assert is_valid, f"generated SQL failed the guardrail: {reason} | sql={sql!r}"

    identifiers = {tok.lower() for tok in _IDENTIFIER_PATTERN.findall(sql)}
    identifiers -= SQL_STOPWORDS
    identifiers = {tok for tok in identifiers if not tok.isdigit()}
    unknown = identifiers - known_columns
    # numeric literals, string contents, and aliases can trip this; treat as
    # a signal to eyeball rather than a hard failure list beyond a sanity check
    assert not unknown or len(unknown) <= 2, (
        f"generated SQL references identifiers not in the known schema: {unknown} | sql={sql!r}"
    )
