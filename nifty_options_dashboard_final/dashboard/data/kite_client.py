# data/kite_client.py
# Single Kite Connect gateway — all pages import from here.
# Never instantiate KiteConnect anywhere else.

import os
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache

import streamlit as st

log = logging.getLogger(__name__)


def _get_kite():
    """
    Return a fully authenticated KiteConnect instance.
    Tries streamlit secrets first (dashboard), then env vars (GitHub Actions).
    """
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        raise RuntimeError("kiteconnect not installed. Run: pip install kiteconnect")

    # Pull credentials
    api_key      = _get_secret("KITE_API_KEY")
    access_token = _get_secret("KITE_ACCESS_TOKEN")

    if not api_key or not access_token:
        raise ValueError(
            "KITE_API_KEY and KITE_ACCESS_TOKEN must be set.\n"
            "  Streamlit: .streamlit/secrets.toml\n"
            "  GitHub Actions: Repository Secrets\n"
            "  Local: .env file"
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def _get_secret(key: str) -> str | None:
    """Read from Streamlit secrets, then environment variables."""
    # Streamlit dashboard context
    try:
        return st.secrets.get(key)
    except Exception:
        pass
    # GitHub Actions / local .env context
    return os.environ.get(key)


def get_kite():
    """
    Session-cached Kite instance for Streamlit.
    In GitHub Actions context, call _get_kite() directly.
    """
    if "kite" not in st.session_state:
        st.session_state["kite"] = _get_kite()
    return st.session_state["kite"]


def get_kite_action() -> object:
    """
    Direct Kite instance for GitHub Actions scripts (no session_state).
    """
    return _get_kite()
