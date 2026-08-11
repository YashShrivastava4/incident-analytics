"""Executes guardrail-approved SQL through the read-only role."""
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("query_executor")

STATEMENT_TIMEOUT = "5s"


def execute_query(sql: str, database_url: str):
    """
    database_url must be the chatbot_readonly connection string, never the
    full-access one, that role restriction is Layer 1 of the guardrail.
    Returns (success, result_df_or_None, error_message_or_None).
    """
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))
            result = conn.execute(text(sql))
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        return True, df, None
    except SQLAlchemyError as exc:
        # covers permission errors (Layer 1 rejecting a write), hallucinated
        # column/table names, and statement_timeout hits
        error_message = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
        logger.warning("query failed: %s | sql=%r", error_message, sql)
        return False, None, error_message
    finally:
        engine.dispose()
