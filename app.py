"""
Streamlit entrypoint. Four pages off one sidebar: the NL-to-SQL assistant
(with a query-free KPI overview always visible), a guardrail Test Lab, a
live data dictionary, and an About page.

Page navigation and the sidebar overview are cosmetic — everything that
touches the database or the LLM still goes through the same src/ modules
Phase 5-10 built (schema_context, sql_generator, guardrail, query_executor,
insight_generator), unchanged in behavior. dashboard_metrics.py is the one
new data path, and it's fixed SQL we wrote, not model output, so it never
touches the guardrail.
"""
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import time
from groq import Groq

from src.schema_context import build_schema_context, get_data_dictionary, FEW_SHOT_EXAMPLES
from src.sql_generator import generate_sql
from src.guardrail import validate_sql
from src.query_executor import execute_query
from src.insight_generator import generate_insight
from src.dashboard_metrics import get_overview_metrics, get_monthly_trend
from src.chart_utils import build_result_chart
from src.test_lab import TEST_CASES

st.set_page_config(page_title="Incident Analytics Assistant", page_icon="📊", layout="wide")

ACCENT = "#7C6CF0"
SAMPLE_QUESTIONS = [ex["question"] for ex in FEW_SHOT_EXAMPLES[:4]]
NAV_PAGES = [
    ("🤖", "Ask Assistant"),
    ("🧪", "Test Lab"),
    ("📖", "Data Dictionary"),
    ("ℹ️", "About"),
]

# Global type scale: rem units are relative to the <html> root, not to any
# Streamlit container, so this is the one CSS rule that reliably resizes
# every widget's text app-wide without touching Streamlit's internal DOM
# classes. Adjust the percentage directly if this still isn't the size you
# want — 100% is Streamlit's untouched default.
# The rest is CSS for elements this file renders itself (KPI cards, nav
# buttons) — not overrides of Streamlit's internal component classes, so
# there's nothing here that a Streamlit version bump could silently break.
st.markdown(
    """
    <style>
    html { font-size: 92%; }
    div.block-container { padding-top: 2rem; }
    div[data-testid="stVerticalBlockBorderWrapper"] button { text-align: left; }
    </style>
    """,
    unsafe_allow_html=True,
)

# secrets only, never hardcoded. st.secrets["DATABASE_URL"] is the chatbot_readonly
# pooled connection string per .streamlit/secrets.toml.example - the same credential
# as .env's DATABASE_URL_POOLED, just read through Streamlit's own secrets system
# instead of python-dotenv. Never the DATABASE_URL_DIRECT full-access role.
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    CHATBOT_DB_URL = st.secrets["DATABASE_URL"]
except KeyError as exc:
    st.error(f"Missing secret: {exc}. Set it in .streamlit/secrets.toml locally or Streamlit Cloud's secrets manager.")
    st.stop()


@st.cache_resource
def get_groq_client():
    return Groq(api_key=GROQ_API_KEY)


@st.cache_data(ttl=3600)
def get_schema_context():
    return build_schema_context(CHATBOT_DB_URL)


@st.cache_data(ttl=600)
def get_overview():
    return get_overview_metrics(CHATBOT_DB_URL)


@st.cache_data(ttl=600)
def get_trend():
    return get_monthly_trend(CHATBOT_DB_URL)


@st.cache_data(ttl=3600)
def get_dictionary():
    return get_data_dictionary(CHATBOT_DB_URL)


client = get_groq_client()

with st.spinner("Waking up the database..."):
    schema_context = get_schema_context()
    overview = get_overview()


def run_pipeline(question: str) -> dict:
    """
    The full question -> SQL -> guardrail -> execution -> insight flow, as a
    single function so Ask Assistant and the Test Lab's "pipeline" tests call
    the exact same code, not two copies of it.
    """
    trace = {
        "question": question,
        "sql": None,
        "guardrail_valid": None,
        "guardrail_reason": None,
        "success": False,
        "result_df": None,
        "error_message": None,
        "insight": None,
    }

    trace["sql"] = generate_sql(question, schema_context, client)

    if trace["sql"].strip().upper() == "NO_QUERY":
        return trace

    is_valid, reason = validate_sql(trace["sql"])
    trace["guardrail_valid"] = is_valid
    trace["guardrail_reason"] = reason
    if not is_valid:
        return trace

    success, result_df, error_message = execute_query(trace["sql"], CHATBOT_DB_URL)

    if not success:
        # one retry, feeding the DB error back to the model, per the guardrail spec
        retry_sql = generate_sql(question, schema_context, client, prior_error=error_message)
        retry_valid, retry_reason = validate_sql(retry_sql)
        if retry_valid:
            success, result_df, error_message = execute_query(retry_sql, CHATBOT_DB_URL)
            trace["sql"] = retry_sql
        trace["guardrail_valid"] = retry_valid
        trace["guardrail_reason"] = retry_reason

    trace["success"] = success
    trace["result_df"] = result_df
    trace["error_message"] = error_message

    if success and result_df is not None and not result_df.empty:
        trace["insight"] = generate_insight(question, result_df, client)

    return trace


def render_chart(df: pd.DataFrame):
    """Only charts results shaped like a time series or one category + one
    measure — most query results (single-row aggregates, wide tables) aren't
    chartable, and that's fine; the table below still shows the real numbers."""
    fig = build_result_chart(df)
    if fig is not None:
        st.pyplot(fig)
        plt.close(fig)


def render_kpi_card(icon: str, label: str, value: str):
    """Hand-rolled instead of st.metric so the icon can sit in its own corner,
    matching the reference layout. `value`/`label` are always numbers/strings
    we computed ourselves (never raw user input), so the inline HTML here
    isn't an injection risk — see notes.md."""
    with st.container(border=True):
        col_text, col_icon = st.columns([5, 1])
        with col_text:
            st.caption(label)
            st.markdown(f"<div style='font-size:1.35rem; font-weight:700; line-height:1.2;'>{value}</div>", unsafe_allow_html=True)
        with col_icon:
            st.markdown(f"<div style='font-size:1.2rem; text-align:right;'>{icon}</div>", unsafe_allow_html=True)


def render_insight_cards(insight: dict):
    with st.container(border=True):
        st.markdown("**🔍 WHAT HAPPENED**")
        st.write(insight["what_happened"])
    with st.container(border=True):
        st.markdown("**⚠️ WHY IT MATTERS**")
        st.write(insight["why_it_matters"])
    with st.container(border=True):
        st.markdown("**✅ RECOMMENDED ACTION**")
        st.write(insight["recommended_action"])


def render_pipeline_result(trace: dict):
    if trace["sql"] is None:
        return

    if trace["sql"].strip().upper() == "NO_QUERY":
        st.warning("I can't answer that from this dataset. Try rephrasing, or ask about SLA, resolution time, volume, or assignment groups.")
        return

    if trace["guardrail_valid"] is False:
        # deliberately not showing the SQL or the exact guardrail reason here —
        # this page is public-facing, keep rejection messages plain. The Test
        # Lab page shows the full trace on purpose, this one doesn't.
        st.error("That question produced a query I'm not allowed to run. Try rephrasing it as a simple lookup or aggregate question.")
        return

    if not trace["success"]:
        st.error("I couldn't get a working query for that question. Try rephrasing it or asking something more specific.")
        return

    tab_answer, tab_sql, tab_insights = st.tabs(["📊 Answer", "🗄️ Generated SQL", "💡 Insights"])

    with tab_answer:
        render_chart(trace["result_df"])
        st.dataframe(trace["result_df"], width="stretch")
        csv_bytes = trace["result_df"].to_csv(index=False).encode("utf-8")
        st.download_button("Export CSV", csv_bytes, file_name="query_result.csv", mime="text/csv")

    with tab_sql:
        st.code(trace["sql"], language="sql")

    with tab_insights:
        if trace["insight"]:
            render_insight_cards(trace["insight"])
        else:
            st.caption("No insight generated for this result.")


def render_ask_assistant():
    st.title("👋 Hello! I'm your Incident Analytics Assistant")
    st.caption("Ask questions about the incident dataset in plain English. I'll generate SQL and provide insights.")

    if "question_input" not in st.session_state:
        st.session_state.question_input = ""
    if "trigger_ask" not in st.session_state:
        st.session_state.trigger_ask = False

    # apply a chip's pending value BEFORE the text_input with this key is
    # instantiated below — session_state for a widget's own key can only be
    # written before that widget exists in a given run, never after. Writing
    # it after (the old code did this inside the button's own if-block, which
    # runs after the text_input above it had already rendered) is exactly
    # what raised the StreamlitAPIException.
    if "pending_question" in st.session_state:
        st.session_state.question_input = st.session_state.pop("pending_question")

    with st.form("ask_form", border=False):
        question = st.text_input(
            "What would you like to know?",
            key="question_input",
            placeholder="e.g. What's the SLA compliance rate for Critical priority incidents?",
        )
        # st.form submits on Enter from any field inside it by default, which
        # is what was missing before — a bare st.text_input + a separate
        # st.button never wired Enter to anything.
        ask_clicked = st.form_submit_button("Ask", type="primary")

    st.caption("Try asking:")
    chip_cols = st.columns(len(SAMPLE_QUESTIONS))
    for col, sample_question in zip(chip_cols, SAMPLE_QUESTIONS):
        if col.button(sample_question, width="stretch"):
            st.session_state.pending_question = sample_question
            st.session_state.trigger_ask = True
            st.rerun()

    run_now = ask_clicked or st.session_state.trigger_ask
    st.session_state.trigger_ask = False

    st.divider()

    if "request_times" not in st.session_state:
        st.session_state.request_times = []

    now = time.time()
    st.session_state.request_times = [t for t in st.session_state.request_times if now - t < 60]

    if len(st.session_state.request_times) >= 7 and run_now:
        st.warning("You're sending questions too quickly. Please wait a moment.")
        st.stop()

    st.session_state.request_times.append(now)

    if run_now and question:
        with st.spinner("Generating SQL, running the query, and summarizing..."):
            trace = run_pipeline(question)
        render_pipeline_result(trace)


def render_test_lab():
    st.title("🧪 Test Lab")
    st.caption(
        "Curated test cases for the assistant's core capability and its safety guardrails. "
        "Nothing here is a canned result — every button below calls the real pipeline, live."
    )

    category_badges = {
        "Core capability": "⚙️ Core capability",
        "Schema robustness": "🧬 Schema robustness",
        "Safety guardrail": "🛡️ Safety guardrail",
    }

    for case in TEST_CASES:
        with st.container(border=True):
            st.markdown(f"**{case['title']}**")
            st.caption(category_badges.get(case["category"], case["category"]))
            st.write(case["explains"])

            if case["mode"] == "pipeline":
                st.code(case["question"], language="text")
            else:
                st.code(case["sql"], language="sql")

            if st.button("Run test", key=f"run_{case['id']}"):
                st.session_state[f"result_{case['id']}"] = _run_test_case(case)

            result = st.session_state.get(f"result_{case['id']}")
            if result is not None:
                _render_test_result(case, result)


def _run_test_case(case: dict) -> dict:
    if case["mode"] == "guardrail_direct":
        is_valid, reason = validate_sql(case["sql"])
        return {"mode": "guardrail_direct", "is_valid": is_valid, "reason": reason}

    with st.spinner("Running the real pipeline..."):
        trace = run_pipeline(case["question"])
    return {"mode": "pipeline", "trace": trace}


def _render_test_result(case: dict, result: dict):
    expects_block = case["category"] in ("Safety guardrail", "Schema robustness")

    if result["mode"] == "guardrail_direct":
        if result["is_valid"]:
            st.error("Unexpected: the guardrail accepted this. It should have been rejected.")
        else:
            st.success(f'Blocked before execution — guardrail reason: "{result["reason"]}"')
        return

    trace = result["trace"]
    is_no_query = bool(trace["sql"]) and trace["sql"].strip().upper() == "NO_QUERY"

    st.markdown("**Generated SQL**")
    st.code(trace["sql"] if trace["sql"] else "(none)", language="text" if is_no_query else "sql")

    if is_no_query:
        (st.success if expects_block else st.warning)(
            "Model declined to answer rather than guess — no query was run against the database."
        )
        return

    if trace["guardrail_valid"] is False:
        (st.success if expects_block else st.error)(
            f'Guardrail rejected this before execution — reason: "{trace["guardrail_reason"]}"'
        )
        return

    if not trace["success"]:
        (st.success if expects_block else st.error)(
            f'Execution did not return data — database error: "{trace["error_message"]}"'
        )
        return

    # a real result came back
    if expects_block:
        st.error("⚠️ This executed successfully. For a safety/robustness test, that's unexpected — worth a closer look.")
    else:
        st.success("Executed successfully — the expected outcome for a core-capability test.")

    render_chart(trace["result_df"])
    st.dataframe(trace["result_df"], width="stretch")
    if trace["insight"]:
        render_insight_cards(trace["insight"])


def render_data_dictionary():
    st.title("📖 Data Dictionary")
    st.caption("Every table and view the assistant can query, introspected live from Neon — the same source the LLM prompt is built from.")

    dictionary = get_dictionary()
    if not dictionary:
        st.warning("Couldn't load the schema right now. Check the database connection.")
        return

    for name, columns in dictionary.items():
        st.markdown(f"#### {name}")
        table_df = pd.DataFrame(columns, columns=["Column", "Type", "Description"])
        st.dataframe(table_df, width="stretch", hide_index=True)


def render_about():
    st.title("ℹ️ About this project")
    st.markdown(
        """
This app turns a plain-English question into validated, safely-executed SQL against a real
Postgres database — the guardrail layer, not the chat UI, is the actual engineering deliverable.

**Architecture:** question → Groq (`openai/gpt-oss-120b`) generates SQL → guardrail validates
it → executes as a read-only `chatbot_readonly` role against Neon → result + a structured,
data-grounded takeaway.

**Two independent guardrail layers** stand between this public app and a `DROP TABLE`:
1. **Database level** — the app connects exclusively as `chatbot_readonly`, a Postgres role
   with `SELECT` only. Even a bug in the layer below can't turn into a write.
2. **Application level** — every generated query is parsed with `sqlparse`, confirmed to be
   exactly one `SELECT` statement, and scanned for any DML/DDL keyword, including inside
   subqueries, CTEs, and comments.

Open the **Test Lab** tab to watch both layers in action, live, against the real pipeline.

**Dataset:** a public ServiceNow-style incident event log — 141,712 events reduced to 24,918
distinct incidents.

**Known limitation:** durations are raw calendar-time deltas; there's no business-hours SLA
calendar in this dataset, so nothing here is reported as "business duration."

**Stack:** Python, pandas, PostgreSQL (Neon), SQLAlchemy, Streamlit, Groq, sqlparse.
        """
    )


with st.sidebar:
    st.markdown("### 📊 Incident Analytics Assistant")

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "Ask Assistant"

    st.caption("EXPLORE")
    # A vertical stack of full-width buttons, not st.pills — pills wrap
    # horizontally with no vertical-list option, which didn't match the
    # reference layout. Buttons with type="primary"/"secondary" is a
    # documented, stable API; getting this look via CSS would mean
    # overriding Streamlit's internal radio DOM classes, which aren't a
    # public API and can break silently on a version upgrade.
    for icon, label in NAV_PAGES:
        is_active = st.session_state.nav_page == label
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{label}",
            type="primary" if is_active else "secondary",
            width="stretch",
        ):
            st.session_state.nav_page = label
            st.rerun()
    page = st.session_state.nav_page

    st.divider()
    st.caption("DATASET OVERVIEW")

    if overview:
        render_kpi_card("📊", "Total Incidents", f"{overview['total_incidents']:,}")
        render_kpi_card("📅", "Date Range", f"{overview['earliest_opened']} → {overview['latest_opened']}")

        sla = overview["sla_compliance_rate"]
        render_kpi_card("✅", "SLA Compliance", f"{sla:.1%}" if sla is not None else "—")

        median = overview["median_resolution_hours"]
        render_kpi_card("⏱️", "Median Resolution", f"{median:.1f} hrs" if median is not None else "—")
    else:
        st.caption("Overview metrics unavailable — check the database connection.")

    st.divider()
    st.caption("🟢 Connected to Neon DB")
    st.caption("All times in hours unless specified otherwise.")


if page == "Ask Assistant":
    render_ask_assistant()
elif page == "Test Lab":
    render_test_lab()
elif page == "Data Dictionary":
    render_data_dictionary()
else:
    render_about()

st.divider()
st.caption("Data source: incidents table · Powered by Groq & Neon PostgreSQL")
