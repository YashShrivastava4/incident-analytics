# Incident Analytics & NL-to-SQL Assistant

Portfolio project #2 of 3. Domain: IT operations analytics + applied GenAI (text-to-SQL) over the
"Incident Management Process enriched event log" dataset (Kaggle).

Two consumers, one source of truth: a Power BI dashboard and a Streamlit NL→SQL chatbot, both
reading from the same cleaned Postgres tables/views. The core deliverable is the two-layer
guardrail that keeps the chatbot's LLM-generated SQL from being able to touch anything but
read-only, validated SELECT statements — not the dashboard or the chat UI themselves.

## Status

- [x] Phase 0 — environment setup (this scaffold)
- [ ] Phase 1 — data profiling (**blocked**: uploaded CSV has 119,998 rows / 20,769 distinct
      incidents, not the expected 141,712 / 24,918 — confirming correct dataset version before
      proceeding)
- [ ] Phase 2 — cleaning + incident-level reduction + Postgres load
- [ ] Phase 3 — KPI views
- [ ] Phase 4 — Power BI dashboard
- [ ] Phase 5 — schema context builder
- [ ] Phase 6 — NL → SQL (Groq, `openai/gpt-oss-120b`)
- [ ] Phase 7 — guardrails
- [ ] Phase 8 — Streamlit deployment
- [ ] Phase 9 — testing
- [ ] Phase 10 — documentation

## Setup (local)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # fill in real values
cp .streamlit/secrets.toml.example .streamlit/secrets.toml  # fill in real values
```

`.env` and `.streamlit/secrets.toml` are gitignored — never commit either, even to a private repo.

## Database

Hosted Postgres on Neon (free tier). Two roles:

- Your own full-access role — used for loading data and DDL. Direct connection string.
- `chatbot_readonly` — `GRANT SELECT` only, no write/DDL privileges, enforced by Postgres itself.
  Used exclusively by the Streamlit app and as Layer 1 of the guardrail. Pooled connection string.

See `sql/roles.sql` for setup and the verification query that proves the read-only role actually
can't write.

## Repo layout

```
incident-analytics/
├── data/raw/            # original Kaggle CSV (tracked in git — no private info)
├── data/processed/      # cleaned CSVs, if exported (tracked in git)
├── sql/                 # schema, views, role setup
├── src/                 # cleaning, schema context, SQL generation, guardrail, execution, insights
├── app.py                # Streamlit entrypoint
├── powerbi/              # .pbix dashboard
├── tests/                # pytest — guardrail tests are the priority
├── notebooks/            # EDA
├── requirements.txt
└── .env.example / .streamlit/secrets.toml.example
```

## Known limitations

(to be filled in as build progresses — e.g. no business-hours SLA calendar, free-tier rate limits,
free-tier DB cold-start latency)
