"""Loads .env before any test runs. pytest does not do this on its own,
and .streamlit/secrets.toml is a separate system Streamlit reads - it has
no effect here at all."""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
