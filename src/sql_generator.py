"""Text-to-SQL via Groq. Model is openai/gpt-oss-120b, not the deprecated Llama one."""
import re
import logging
from groq import Groq

logger = logging.getLogger("sql_generator")

MODEL = "openai/gpt-oss-120b"

SYSTEM_INSTRUCTION = (
    "Output only a single valid Postgres SELECT statement that answers the "
    "question. No prose, no explanation, no markdown code fences. If the "
    "question cannot be answered with the given schema, output exactly: "
    "NO_QUERY"
)

# gpt-oss-120b's exact fence/commentary habits aren't verified in this repo yet,
# strip defensively regardless of what the model actually does
_FENCE_PATTERN = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _clean_sql_output(raw: str) -> str:
    text = raw.strip()
    text = _FENCE_PATTERN.sub("", text).strip()
    # drop a leading "SQL:" label if the model adds one despite instructions
    text = re.sub(r"^SQL:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def generate_sql(question: str, schema_context: str, client: Groq, prior_error: str = None) -> str:
    """
    Returns cleaned SQL text (or 'NO_QUERY'). Caller is responsible for
    running this through guardrail.validate_sql before executing anything.
    """
    user_content = f"Question: {question}"
    if prior_error:
        # single retry path: feed the exact DB error back, cap at one retry in the caller
        user_content += (
            f"\n\nThe previous SQL attempt failed with this Postgres error:\n{prior_error}\n"
            "Fix the query."
        )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": f"{schema_context}\n\n{SYSTEM_INSTRUCTION}"},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )

    raw = response.choices[0].message.content
    cleaned = _clean_sql_output(raw)
    logger.info("generated SQL for question=%r: %r", question, cleaned)
    return cleaned
