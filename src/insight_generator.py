"""Generates a one-line plain-English insight from a query result."""
import logging
import pandas as pd
from groq import Groq

logger = logging.getLogger("insight_generator")

# duplicated from sql_generator.py rather than imported, so this file works
# whether it's imported as part of the src package (app.py) or loaded
# standalone (tests) without an import path depending on the caller
MODEL = "openai/gpt-oss-120b"

MAX_ROWS_IN_PROMPT = 20  # keep the prompt small, don't dump a huge result set into it


def generate_insight(question: str, result_df: pd.DataFrame, client: Groq) -> str:
    if result_df is None or result_df.empty:
        return "No rows matched this question."

    preview = result_df.head(MAX_ROWS_IN_PROMPT).to_csv(index=False)
    truncated_note = "" if len(result_df) <= MAX_ROWS_IN_PROMPT else f"\n(showing first {MAX_ROWS_IN_PROMPT} of {len(result_df)} rows)"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Write exactly one short sentence summarizing the key takeaway "
                    "from this query result. No preamble, no restating the question."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nResult:\n{preview}{truncated_note}",
            },
        ],
        temperature=0.2,
    )
    insight = response.choices[0].message.content.strip()
    logger.info("insight for question=%r: %r", question, insight)
    return insight
