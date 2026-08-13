"""Generates a structured, data-grounded takeaway from a query result."""
import json
import logging
import re
import pandas as pd
from groq import Groq

logger = logging.getLogger("insight_generator")

# duplicated from sql_generator.py rather than imported, so this file works
# whether it's imported as part of the src package (app.py) or loaded
# standalone (tests) without an import path depending on the caller
MODEL = "openai/gpt-oss-120b"

MAX_ROWS_IN_PROMPT = 20  # keep the prompt small, don't dump a huge result set into it

# gpt-oss-120b's exact fence/commentary habits aren't verified in this repo,
# strip defensively regardless of what the model actually does
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

SYSTEM_INSTRUCTION = (
    "You analyze one query result at a time from an IT incident-management dataset. "
    "Respond with ONLY a JSON object, no prose outside it, no markdown fences, with "
    "exactly these three keys:\n"
    '  "what_happened": the key finding, stated directly from the result. One sentence.\n'
    '  "why_it_matters": the operational or business significance of that finding. One sentence.\n'
    '  "recommended_action": one concrete, reasonable next step the finding supports.\n'
    "Stay grounded in the result given — never state a fact the result doesn't show. If the "
    "data can't establish why something happened, say that plainly in why_it_matters instead "
    "of guessing at a cause."
)

# used when there's nothing to summarize, or the model's output didn't parse —
# both are honest fallbacks, not fabricated structure
FALLBACK_NO_ROWS = {
    "what_happened": "No rows matched this question.",
    "why_it_matters": "There's nothing to assess from an empty result.",
    "recommended_action": "Try rephrasing the question or broadening the filters.",
}

FALLBACK_PARSE_ERROR = {
    "what_happened": "The result loaded, but a written summary couldn't be generated this time.",
    "why_it_matters": "This is a formatting issue with the summary step, not with the query result itself.",
    "recommended_action": "The data above is still accurate — try asking again for a written takeaway.",
}


def _clean_json_output(raw: str) -> str:
    text = raw.strip()
    text = _FENCE_PATTERN.sub("", text).strip()
    return text


def generate_insight(question: str, result_df: pd.DataFrame, client: Groq) -> dict:
    """
    Returns {"what_happened", "why_it_matters", "recommended_action"}, all strings.
    Falls back to a plain, honest message rather than inventing structure the
    model didn't actually return.
    """
    if result_df is None or result_df.empty:
        return dict(FALLBACK_NO_ROWS)

    preview = result_df.head(MAX_ROWS_IN_PROMPT).to_csv(index=False)
    truncated_note = "" if len(result_df) <= MAX_ROWS_IN_PROMPT else f"\n(showing first {MAX_ROWS_IN_PROMPT} of {len(result_df)} rows)"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": f"Question: {question}\n\nResult:\n{preview}{truncated_note}",
            },
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content
    cleaned = _clean_json_output(raw)

    try:
        parsed = json.loads(cleaned)
        insight = {
            "what_happened": str(parsed["what_happened"]).strip(),
            "why_it_matters": str(parsed["why_it_matters"]).strip(),
            "recommended_action": str(parsed["recommended_action"]).strip(),
        }
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("insight JSON did not parse: %s | raw=%r", exc, raw)
        return dict(FALLBACK_PARSE_ERROR)

    logger.info("insight for question=%r: %r", question, insight)
    return insight
