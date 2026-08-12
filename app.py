"""Streamlit entrypoint. Ask a question in plain English, get back a table + insight."""
import streamlit as st
from groq import Groq

from src.schema_context import build_schema_context
from src.sql_generator import generate_sql
from src.guardrail import validate_sql
from src.query_executor import execute_query
from src.insight_generator import generate_insight

st.set_page_config(page_title="Incident Analytics Assistant", page_icon="📊")
st.title("Incident Analytics Assistant")
st.caption("Ask a question about the incident dataset in plain English.")

# secrets only, never hardcoded. st.secrets["DATABASE_URL"] is the chatbot_readonly
# pooled connection string per .streamlit/secrets.toml.example - the same credential
# as .env's DATABASE_URL_POOLED, just read through Streamlit's own secrets system
# instead of python-dotenv. Never the DATABASE_URL_DIRECT full-access role.
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    CHATBOT_DB_URL = st.secrets["DATABASE_URL"]  # chatbot_readonly pooled string, see secrets.toml.example
except KeyError as exc:
    st.error(f"Missing secret: {exc}. Set it in .streamlit/secrets.toml locally or Streamlit Cloud's secrets manager.")
    st.stop()


@st.cache_resource
def get_groq_client():
    return Groq(api_key=GROQ_API_KEY)


@st.cache_data(ttl=3600)
def get_schema_context():
    return build_schema_context(CHATBOT_DB_URL)


client = get_groq_client()

with st.spinner("Waking up the database..."):
    schema_context = get_schema_context()

question = st.text_input("Your question", placeholder="e.g. What's the SLA compliance rate for Critical priority incidents?")

if st.button("Ask", type="primary") and question:
    with st.spinner("Generating SQL..."):
        sql = generate_sql(question, schema_context, client)

    if sql.strip().upper() == "NO_QUERY":
        st.warning("I can't answer that from this dataset. Try rephrasing, or ask about SLA, resolution time, volume, or assignment groups.")
        st.stop()

    is_valid, reason = validate_sql(sql)
    if not is_valid:
        # never surface the raw rejection reason as a stack trace-y message,
        # keep it plain for a public-facing app
        st.error("That question produced a query I'm not allowed to run. Try rephrasing it as a simple lookup or aggregate question.")
        st.stop()

    with st.spinner("Running query..."):
        success, result_df, error_message = execute_query(sql, CHATBOT_DB_URL)

    if not success:
        # one retry, feeding the DB error back to the model, per the guardrail spec
        with st.spinner("First attempt failed, retrying once..."):
            retry_sql = generate_sql(question, schema_context, client, prior_error=error_message)
            is_valid, reason = validate_sql(retry_sql)
            if is_valid:
                success, result_df, error_message = execute_query(retry_sql, CHATBOT_DB_URL)
                sql = retry_sql

    if not success:
        st.error("I couldn't get a working query for that question. Try rephrasing it or asking something more specific.")
        st.stop()

    with st.expander("Generated SQL"):
        st.code(sql, language="sql")

    st.dataframe(result_df, use_container_width=True)

    with st.spinner("Summarizing..."):
        insight = generate_insight(question, result_df, client)
    st.info(insight)
