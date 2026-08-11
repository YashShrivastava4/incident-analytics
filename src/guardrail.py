"""SQL validation layer. Runs before any generated SQL touches the database."""
import logging
import re
import sqlparse
from sqlparse.sql import TokenList
from sqlparse.tokens import Keyword, DML, Comment

logger = logging.getLogger("guardrail")

# admin/write keywords, never allowed anywhere in the query
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "COPY", "VACUUM", "EXECUTE",
    "CALL", "MERGE", "REINDEX", "CLUSTER", "LISTEN", "NOTIFY",
}

# raw-text regex backstop, word-boundaried, case-insensitive
_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)


def _flatten_tokens(token_list):
    """Yield every leaf token, descending into subqueries/CTEs/parens."""
    for token in token_list.tokens:
        if isinstance(token, TokenList):
            yield from _flatten_tokens(token)
        else:
            yield token


def _contains_forbidden_token(statement):
    for token in _flatten_tokens(statement):
        value = token.value.strip().upper()
        if not value:
            continue
        # keyword or comment tokens both get checked, guide asks for both
        if token.ttype in (Keyword, DML) or token.ttype in Comment:
            if value in FORBIDDEN_KEYWORDS:
                return value
            # comments can contain multi-word text, check substrings too
            if token.ttype in Comment and _FORBIDDEN_PATTERN.search(value):
                match = _FORBIDDEN_PATTERN.search(value)
                return match.group(1).upper()
    return None


def validate_sql(sql: str):
    """
    Returns (is_valid, reason).
    reason is None when valid, otherwise a short explanation for logging/UI.
    """
    if sql is None or not sql.strip():
        reason = "empty query"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    # strip a single trailing semicolon before counting statements, a lone
    # trailing ';' on an otherwise-single statement isn't a multi-statement attempt
    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1]

    statements = [s for s in sqlparse.parse(stripped) if s.value.strip()]

    if len(statements) == 0:
        reason = "no valid SQL statement found"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    if len(statements) > 1:
        reason = "multiple statements in one query"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    statement = statements[0]

    # raw-text backstop first, catches anything odd tokenization might miss
    raw_match = _FORBIDDEN_PATTERN.search(stripped)
    if raw_match:
        reason = f"forbidden keyword '{raw_match.group(1).upper()}' found in query text"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    # tokenized check, walks into subqueries/CTEs/comments
    forbidden = _contains_forbidden_token(statement)
    if forbidden:
        reason = f"forbidden keyword '{forbidden}' found in query"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    stmt_type = statement.get_type()
    if stmt_type != "SELECT":
        reason = f"statement type '{stmt_type}' is not SELECT"
        logger.warning("REJECTED: %s | sql=%r", reason, sql)
        return False, reason

    return True, None
