# Incident Analytics & NL-to-SQL Assistant

IT incident analytics on a public ServiceNow-style event log, built two ways: a Power BI
dashboard for classical BI, and a Streamlit chat interface that turns a plain-English question
into validated, safely-executed SQL. The guardrail layer — not the dashboard, not the chatbot UI
— is the actual engineering deliverable here: an LLM should never get to run arbitrary SQL
against a real database, and this project is a demonstration of what stops that from happening.

## Status

| Phase | Status |
|---|---|
| 0 — Environment setup | Done |
| 1 — Data profiling | Done |
| 2 — Cleaning + incident-level reduction + Postgres load | Done |
| 3 — KPI views | Done |
| 4 — Power BI dashboard | Done |
| 5 — Schema context builder | Drafted, pending validation against live schema |
| 6 — NL → SQL (Groq) | Drafted, pending validation |
| 7 — Guardrails | Drafted, adversarial test suite passing locally |
| 8 — Streamlit deployment | Drafted, not yet deployed |
| 9 — Testing | Drafted, DB/API-dependent tests pending a live run |
| 10 — Documentation | This file |

## Architecture

```
Kaggle CSV (raw event log, 141,712 rows)
        |
        v
Python/pandas cleaning + incident-level reduction
        |
        v
Hosted Postgres (Neon, free tier)
   |-- raw_events   (untouched event log, audit/traceability only)
   |-- incidents    (one row per incident, the analytical table)
   |-- views: v_sla_by_priority, v_resolution_time, v_volume_trend, etc.
   `-- role: chatbot_readonly (GRANT SELECT only, enforced by Postgres itself)
        |
        |------------------------------|
        v                              v
Power BI Desktop                 Streamlit app
(full-access role,               (question -> Groq generates SQL
 pooled connection)                -> guardrail validates
                                    -> executes as chatbot_readonly
                                    -> result + one-line insight)
```

Both consumers read from the same `incidents` table and the same six KPI views, so a number
shown on the dashboard and a number returned by the chatbot should never disagree because they
were computed two different ways.

## The incident-level reduction

The source file is an **event log**, not an incident table: 141,712 rows but only 24,918
distinct incidents, because each incident logs 5–8+ rows as it moves through its lifecycle
(New → In Progress → Resolved → Closed, reassignments, reopens). Grouping by incident number and
counting rows without reducing first inflates every count by roughly 5.7x — the same shape of
bug as the `customer_id` vs. `customer_unique_id` trap in the CLV project's OLIST dataset.

The fix: take the **last** row per incident (by `sys_updated_at`) for cumulative/final-state
fields (`incident_state`, `made_sla`, `closed_code`, `resolved_at`, `closed_at`, `priority`), the
**first** row for fields set at open time (`opened_at`, `category`), and `MAX()` for running
counters (`reassignment_count`, `reopen_count`, `sys_mod_count`). Everything downstream —
dashboard, chatbot schema — reads from this one reduced table, not the raw event log.

Two other data quirks worth knowing about: missing values are encoded as the literal string
`"?"`, not a true null (a naive `.isnull().sum()` reports zero missingness and is wrong), and
timestamps are `DD/MM/YYYY`, which silently misparses under a default date parser for any row
where the day happens to be ≤ 12. Both are handled explicitly in the cleaning step rather than
assumed away.

## Two-layer guardrail

An LLM-generated SQL string never runs against the database on trust. Two independent layers,
deliberately redundant — neither is allowed to be the only thing standing between a public
Streamlit app and a `DROP TABLE`:

1. **Database level:** the chatbot connects exclusively as `chatbot_readonly`, a Postgres role
   with `GRANT SELECT` only, nothing else. Even if the app-level check below has a bug, Postgres
   itself rejects any `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER` at the permissions level.
2. **Application level:** every generated query is parsed with `sqlparse` before execution —
   confirmed to be exactly one statement, confirmed to be a `SELECT`, and scanned (including
   inside subqueries, CTEs, and comments) for any DML/DDL/admin keyword. Multi-statement payloads
   are rejected outright rather than silently running just the first statement.

`tests/test_guardrail.py` covers this with adversarial inputs — multi-statement injection, DML
disguised inside a CTE or subquery, a prompt-injection attempt embedded in the natural-language
question itself — plus a test that connects as `chatbot_readonly` directly and asserts a
`DELETE` raises a permissions error, which is what actually proves layer 1 holds rather than just
looking safe.

## Known limitations

- **No business-hours SLA calendar.** `resolution_time_hours` and `time_to_close_hours` are raw
  calendar-time deltas between timestamps present in the data. There's no 24×7 vs. 8×5 field to
  model business hours against, so nothing here is reported as "business duration."
- **Free-tier DB cold start.** Neon's free tier auto-suspends when idle; the first query after
  idle time takes a few seconds. The Streamlit app shows a spinner during this instead of
  appearing to hang.
- **Anonymized identifiers, not decoded ones.** `caller_id`, `assignment_group`, `assigned_to`,
  and `cmdb_ci` are pseudonyms (e.g. `"Caller 2403"`) with no lookup table behind them. Cleaning
  here means normalizing already-anonymized strings, not de-anonymizing anything.
- **Groq free-tier rate limits** apply to both the SQL-generation and insight-generation calls;
  a public deployment link should be treated as a real (if small) attack/quota surface.
- **Single retry on execution error.** If generated SQL fails (e.g. a hallucinated column name),
  the error is fed back to the model once. It does not loop.

## Tech stack

Python, pandas, PostgreSQL (Neon), SQLAlchemy, Streamlit, Groq (`openai/gpt-oss-120b`),
`sqlparse`, pytest, Power BI Desktop.

## Running locally

1. `pip install -r requirements.txt`
2. Set `DATABASE_URL_DIRECT`, `DATABASE_URL_POOLED`, `GROQ_API_KEY` in `.env` (see
   `.env.example`), and `GROQ_API_KEY` + `CHATBOT_DB_URL` (the `chatbot_readonly` **pooled**
   connection string) in `.streamlit/secrets.toml` — never the full-access connection string,
   that would defeat the database-level guardrail.
3. `streamlit run app.py`

## Live deployment

Not yet deployed. Once Phase 8 is live on Streamlit Community Cloud, the link goes here.
