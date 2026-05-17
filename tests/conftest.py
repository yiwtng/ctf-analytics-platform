"""Shared pytest fixtures for all test levels."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform" / "orchestrator"))


# ---------------------------------------------------------------------------
# Configuration for live services (used by smoke/integration/api/e2e)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_config():
    """Connection settings for the live analytics DB."""
    return {
        "host": os.getenv("ANALYTICS_DB_HOST", "localhost"),
        "port": int(os.getenv("ANALYTICS_DB_PORT", "5433")),
        "dbname": os.getenv("ANALYTICS_DB_NAME", "analytics"),
        "user": os.getenv("ANALYTICS_DB_USER", "analytics"),
        "password": os.getenv("ANALYTICS_DB_PASSWORD", "analytics"),
    }


@pytest.fixture(scope="session")
def orchestrator_url():
    """Base URL for the live orchestrator (used by api/smoke/e2e)."""
    return os.getenv("ORCH_BASE", "http://localhost:8001").rstrip("/")


@pytest.fixture
def live_db(db_config):
    """Open a connection to the analytics DB. Skips test if DB not reachable."""
    try:
        import psycopg2
        conn = psycopg2.connect(**db_config, connect_timeout=2)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"analytics DB not reachable: {exc}")


@pytest.fixture
def api_client(orchestrator_url):
    """httpx client pointed at the orchestrator. Skips test if unreachable."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")
    try:
        client = httpx.Client(base_url=orchestrator_url, timeout=5.0)
        r = client.get("/health")
        if r.status_code != 200:
            pytest.skip(f"orchestrator /health returned {r.status_code}")
        yield client
        client.close()
    except Exception as exc:
        pytest.skip(f"orchestrator not reachable: {exc}")


# ---------------------------------------------------------------------------
# Deterministic fixtures for unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_stats():
    """Reference stats dict for testing skill score formulas."""
    return {
        "total_solves": 5,
        "total_wrong_submits": 2,
        "total_started": 4,
        "total_giveups": 0,
        "total_errors": 1,
        "web_request": 8,
        "web_solves": 1,
        "web_wrong_fast": 0,
        "tcp_hello_ok": 2,
        "tcp_malformed": 0,
        "tcp_bad_auth": 1,
        "protocol_solves": 1,
        "ssh_command": 5,
        "ssh_solves": 1,
        "ssh_errors": 0,
        "blue_unique_attempts": 3,
        "blue_opened": 5,
        "blue_solves": 2,
        "blue_wrong": 1,
        "blue_hint_use": 1,
        "excessive_restarts": 0,
    }


@pytest.fixture
def mock_gemini_response():
    """Canned Gemini API response payload."""
    return {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"profile": ["balanced_learner"], "strengths": ["protocol_understanding"], '
                            '"weaknesses": ["web_recon_speed"], "recommendations": ["practice SSH"], '
                            '"summary": "Steady progress overall.", "confidence": "medium"}'
                }]
            }
        }]
    }
