# Incident Analytics & NL-to-SQL Assistant

I built this on a public IT service-desk dataset to explore a question I kept running into while
learning data analysis: dashboards are great until someone asks a question you didn't build a
chart for, and "just wire up an LLM to write SQL" is a great way to hand a stranger on the
internet a `DROP TABLE` button. This project is my attempt at a middle ground — a real dashboard
for the questions I already know matter, and a natural-language assistant for everything else,
sitting behind safety checks I can actually demonstrate rather than just claim.

**🔗 Live app:** [https://incident-analytics-m5eqswqx22dv86crj3dq67.streamlit.app/](https://incident-analytics-m5eqswqx22dv86crj3dq67.streamlit.app/)

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.60-FF4B4B)](https://streamlit.io/)
[![PostgreSQL](https://img.shields.io/badge/postgres-Neon-336791)](https://neon.tech/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Problem Statement

IT service desks generate huge incident logs, but that data usually sits underused between two
extremes. A BI dashboard is powerful but static — it answers the questions its builder thought to
ask, and anything outside that means going back to an analyst for a new query. On the other end,
giving someone an open text box wired straight to an LLM that writes and runs SQL against a live
database is a real risk, not a hypothetical one — a model that will write a `DELETE` when asked,
or one that can be talked into it, is exactly the kind of thing that goes wrong in production.

I wanted something in between: a dashboard for the questions I already know matter, and a
conversational interface for the rest — without trusting the model's output on faith. The
interesting problem here was never "can an LLM write SQL." It obviously can. It's "how do I let
it write SQL against a real database without that database being one bad prompt away from a bad
day." That's what this project is actually about; the chat interface is just the visible part.

## My Solution

I built two things on the same cleaned dataset and the same Postgres database: a five-page Power
BI dashboard for the standard executive-level questions, and a Streamlit app with a
natural-language assistant that sits behind two independent safety checks, plus a page where you
can watch those checks work live instead of taking my word for it.

A few choices worth explaining:
- **Postgres on Neon, not a local database.** A database that only exists on my laptop is
  unreachable once the app is deployed, and Neon's free tier is real Postgres — so the safety
  checks I built are being tested against something real, not a toy.
- **Groq for inference, not OpenAI or Anthropic directly.** Fast responses and a generous free
  tier meant I could iterate on prompts a lot without worrying about API cost.
- **Two independent safety layers, not one.** A database role that physically can't write, plus
  an application-level check — so a bug in either one isn't the only thing standing between a
  public app and a destructive query. More on this below.
- **Streamlit over a custom frontend.** As a one-person project, it got me to something working
  and deployable fastest, without building and hosting a separate API and UI.

```mermaid
flowchart LR
    U["You"] -->|"asks a question"| S["Streamlit App"]
    S -->|"question + schema"| G["Groq (LLM)"]
    G -->|"generated SQL"| S
    S -->|"validated, read-only query"| N["Neon Postgres"]
    N -->|"results"| S
    S -->|"reads incidents table"| P["Power BI Dashboard"]
```


## How It Works

I type a question, an LLM turns it into SQL, that SQL gets checked before it's allowed anywhere
near the database, and only then does it run:

```mermaid
flowchart TD
    A["I ask a question"] --> B["Groq turns it into SQL"]
    B --> C{"Guardrail checks the SQL"}
    C -->|"fails the check"| D["Rejected — nothing<br/>reaches the database"]
    C -->|"passes"| E["Runs as a read-only<br/>database role"]
    E -->|"succeeds"| F["Result"]
    E -->|"fails — e.g. a bad column"| G["Error sent back to<br/>Groq — one retry"]
    G --> C
    F --> H["Groq writes a short takeaway"]
    F --> I["Chart + table shown to me"]
    H --> I
    D --> J["Plain error message shown to me"]
```

The check happens *before* anything touches the database, not after — and if the model asks for a
column that doesn't exist, that's Postgres rejecting it, not a safety-check failure. The dashboard
numbers in the sidebar are computed separately, with fixed SQL I wrote myself, so they load
instantly without needing a model call at all.

## The Two-Layer Guardrail

This is the actual engineering focus of this project, not the chat UI. A generated SQL query
never runs just because a model produced it. Two independent checks sit in between, on purpose —
neither one is allowed to be the only thing stopping a bad query:

1. **The database itself won't allow writes.** The app connects using a Postgres role that only
   has `SELECT` permission. Even if my own code has a bug I haven't found, Postgres itself refuses
   any `INSERT` / `UPDATE` / `DELETE` / `DROP` at the permission level.
2. **Every query is checked before it runs.** I parse it with a real SQL parser — not just
   pattern-matching text — and confirm it's exactly one `SELECT` statement with no destructive
   keyword hidden anywhere, including inside subqueries or comments. Anything else is rejected
   before it reaches the database.

I didn't want to just claim this works, so the app has a **Test Lab** page: five cases you can run
live. Two are normal questions. One asks about a column that doesn't exist, to check the assistant
declines rather than making one up. Two are real attack attempts — a plain-English destructive
request, and a hand-written SQL injection string — and you can watch both get blocked in real
time, with the actual reasoning shown on screen.

## The Data

The source file is an event log, not a table of incidents — 141,712 rows, but only 24,918 actual
incidents, because each incident gets logged again every time its status changes. Group by
incident number and count rows without accounting for this, and every number comes out roughly
5.7x too high. I reduce the event log down to one row per incident before anything else touches
it — the dashboard, the SQL views, and the assistant's schema all read from that reduced table,
never the raw log.

Two smaller quirks I had to handle explicitly: missing values are stored as the text `"?"`
instead of a real blank, so a standard missing-value check silently reports zero missing data when
there's actually a lot; and dates are day-first (`31/12/2016`), which a default parser misreads
for any date where the day happens to be 12 or under.

## Tech Stack

| Tool | Role | Why |
|---|---|---|
| Python + pandas | Cleaning & incident-level reduction | Standard for this kind of work |
| PostgreSQL (Neon) | Hosted database | Has to be reachable from a deployed app, not my laptop |
| SQLAlchemy + psycopg2 | Database connectivity | Reliable, well-supported pairing |
| Groq (`openai/gpt-oss-120b`) | Generates SQL + takeaways | Fast and free enough to iterate a lot |
| sqlparse | Validates generated SQL | A real parser, not regex guesswork |
| Streamlit | The whole app | Fastest way for one person to ship something real |
| matplotlib | Charts | More styling control than Streamlit's built-in charts |
| Power BI | A second, classic dashboard | Industry-standard BI tool, relevant to the roles I'm targeting |
| pytest | Automated tests | Standard Python testing |

## Key Features

- Ask a question in plain English, get real SQL run against a real database.
- Two independent, tested safety layers — with a Test Lab page to watch them work live.
- Dashboard numbers that load instantly on open, no model call needed just to see them.
- Auto-generated charts for results shaped like a time series or a category breakdown.
- Plain-language takeaways on results: what happened, why it matters, what to do next.
- A live data dictionary that reads the schema directly, so it can't go stale.
- A companion five-page Power BI dashboard on the same underlying data.

## Folder Structure

```
incident-analytics/
├── app.py                        # Streamlit entrypoint: dashboard + assistant + Test Lab
├── requirements.txt
├── .env.example                  # template for local pipeline/test environment variables
├── .streamlit/
│   ├── config.toml               # app theme
│   └── secrets.toml.example      # template for GROQ_API_KEY + DATABASE_URL
├── data/
│   ├── raw/                      # source CSV goes here (gitignored)
│   └── processed/                # intermediate cleaned files (gitignored)
├── notebooks/
│   └── 00_data_profiling.ipynb
├── powerbi/
│   └── incident_analytics_dashboard.pbix
├── sql/
│   ├── schema.sql                # table definitions
│   ├── views.sql                 # the six KPI views the dashboard and assistant both read from
│   └── roles.sql                 # the read-only database role (guardrail layer 1)
├── src/
│   ├── clean_and_load.py         # cleans the raw CSV, reduces to incident-level, loads to Neon
│   ├── schema_context.py         # live schema introspection → LLM prompt + data dictionary
│   ├── sql_generator.py          # question → SQL via Groq
│   ├── guardrail.py              # SQL validation (guardrail layer 2)
│   ├── query_executor.py         # runs validated SQL against the read-only role
│   ├── insight_generator.py      # result → short takeaway via Groq
│   ├── dashboard_metrics.py      # fixed SQL for the sidebar KPI cards — no LLM involved
│   ├── chart_utils.py            # auto-charting for query results
│   └── test_lab.py               # the five Test Lab case definitions
└── tests/
    ├── test_cleaning.py
    ├── test_sql_generator.py
    └── test_guardrail.py         # the adversarial safety-check test suite
```

## Running This Locally

```bash
git clone https://github.com/YashShrivastava4/incident-analytics
cd incident-analytics
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in a Groq API key
(free at [console.groq.com](https://console.groq.com)) and a Neon database connection string.
Then:

```bash
streamlit run app.py
```

To run the tests: `pytest tests/ -v`. Most run with no credentials needed; a few that hit the real
Groq API and database are skipped automatically if you haven't set those up.

<details>
<summary><b>Setting up your own database from scratch</b> (if you don't already have access to one)</summary>

1. Create a free [Neon](https://neon.tech) Postgres project.
2. Download the dataset (see [Dataset & Acknowledgments](#dataset--acknowledgments)) into `data/raw/`.
3. Set up `.env` (see `.env.example`) with your database and Groq credentials.
4. Run the setup scripts against your **direct** (full-access) connection string:
   ```bash
   psql "$DATABASE_URL_DIRECT" -f sql/schema.sql
   python src/clean_and_load.py
   psql "$DATABASE_URL_DIRECT" -f sql/views.sql
   psql "$DATABASE_URL_DIRECT" -f sql/roles.sql
   ```
5. In `.streamlit/secrets.toml`, use the **pooled** connection string authenticated as the
   read-only role — not your full-access one.

</details>

## Known Limitations

- **Durations are calendar time, not business hours.** Nothing in this dataset marks business
  hours, so resolution times are raw elapsed time, not "business duration."
- **Free-tier cold starts.** The database sleeps when idle; the first query after a while takes a
  few seconds. The app shows a spinner rather than appearing frozen.
- **IDs are anonymized, not decoded.** Fields like caller or assignment group are already
  pseudonyms (e.g. `"Caller 2403"`) with no way to reverse them — and there shouldn't be.
- **One retry, not a loop.** If a generated query fails, the error goes back to the model exactly
  once. It doesn't keep trying indefinitely.
- **The Test Lab is more transparent than the main assistant, on purpose.** It shows real error
  messages and real rejection reasons so the safety layers are actually verifiable — which also
  means any visitor sees that detail, not just me. A deliberate trade-off, not an oversight.

A few things I'd add if I kept building this: a business-hours calendar for more accurate SLA
numbers, rate limiting on the public deployment, and multi-turn memory so a follow-up like "now
break that down by category" would work without repeating the whole question.

## Screenshots

### Power BI Dashboard

The project includes five Power BI pages covering executive KPIs, SLA performance,
resolution time, workload and assignment patterns, and incident trends.

![Power BI Executive Summary](docs/screenshots/powerbi-executive-summary.png)

<details>
<summary><b>View the remaining four Power BI dashboard pages</b></summary>

#### 2. SLA Performance

![SLA Performance](docs/screenshots/powerbi-sla-performance.png)

#### 3. Resolution Time Analysis

![Resolution Time Analysis](docs/screenshots/powerbi-resolution-time.png)

#### 4. Workload & Assignment

![Workload & Assignment](docs/screenshots/powerbi-workload-assignment.png)

#### 5. Trend Analysis

![Trend Analysis](docs/screenshots/powerbi-trend-analysis.png)

</details>


### Streamlit — Ask Assistant

The natural-language assistant turns questions into SQL, executes validated
read-only queries against PostgreSQL, and returns results with charts and
plain-language insights.

![Ask Assistant — Result & Insights](docs/screenshots/assistant-result-insights.png)

<details>
<summary><b>View SQL generation and additional assistant views</b></summary>

#### Generated SQL

![Generated SQL](docs/screenshots/assistant-generated-sql.png)

#### Chart & Query Result

![Assistant Chart Result](docs/screenshots/assistant-chart-result.png)

</details>


### Streamlit — Test Lab

The Test Lab runs live cases against the same pipeline to demonstrate both
normal query execution and the application's safety checks.

![Test Lab — Safety Guardrails](docs/screenshots/test-lab-safety-guardrails.png)

<details>
<summary><b>View additional Test Lab cases</b></summary>

#### Basic NL-to-SQL Query

![Basic NL-to-SQL Query](docs/screenshots/test-lab-basic-query.png)

#### Schema Robustness

![Schema Robustness](docs/screenshots/test-lab-schema-robustness.png)

#### Complex Analytical Query

![Complex Analytical Query](docs/screenshots/test-lab-complex-query.png)

</details>


## Dataset & Acknowledgments

This project uses the **Incident management process enriched event log** dataset:

> Amaral, C., Fantinato, M., & Peres, S. (2018). *Incident management process enriched event log*
> [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C57S4H

Extracted from the audit system of a real ServiceNow instance at an IT company, anonymized, and
released under a CC BY 4.0 license. 141,712 events across 24,918 incidents, 36 attributes.

## License

The code here is under the [MIT License](LICENSE) — use it, fork it, learn from it. The dataset
itself is licensed separately under CC BY 4.0 by its original authors, cited above.

## About Me

I'm Yash Shrivastava, a final-year Electronics & Telecommunication Engineering student building
toward a data analyst role. This is one of three projects in my portfolio.

[LinkedIn](https://www.linkedin.com/in/yash-shrivastava-a84465246/) · [GitHub](https://github.com/YashShrivastava4) · [yash.shrivastava494@gmail.com](mailto:yash.shrivastava494@gmail.com)