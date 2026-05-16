from flask import Flask, request, Response, render_template_string
import os
import time
import requests

app = Flask(__name__)

FLAG = "flag{344d59b6084a1d4d1ecb89a692fcf13c}"

ORCH_URL = os.getenv("ORCH_URL", "")
USER_ID = os.getenv("USER_ID", "")
CHALLENGE_ID = os.getenv("CHALLENGE_ID", "")
SESSION_ID = os.getenv("SESSION_ID", "")

LOGS: list[str] = []


def emit(event_type: str, **kwargs):
    if not ORCH_URL:
        return
    try:
        requests.post(
            ORCH_URL,
            params={
                "event_type": event_type,
                "user_key": USER_ID,
                "challenge_id": CHALLENGE_ID,
                "session_id": SESSION_ID,
                **kwargs,
            },
            timeout=1.0,
        )
    except Exception:
        pass


BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Internal Search Portal</title>
    <style>
        :root {
            --bg: #0b1020;
            --panel: #121a2b;
            --panel-2: #0f1727;
            --text: #e6eefc;
            --muted: #92a1bd;
            --border: #22314f;
            --accent: #4f7cff;
            --accent-2: #7aa2ff;
            --danger: #ff6b6b;
            --success: #33d17a;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: "Segoe UI", Arial, sans-serif;
            background:
                radial-gradient(circle at top right, rgba(79,124,255,0.10), transparent 22%),
                linear-gradient(180deg, #08101d 0%, #0b1020 100%);
            color: var(--text);
            min-height: 100vh;
        }

        .shell {
            max-width: 980px;
            margin: 48px auto;
            padding: 0 20px;
        }

        .card {
            background: rgba(18, 26, 43, 0.95);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 28px;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }

        .brand {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .brand small {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 11px;
        }

        h1, h2 {
            margin: 0;
            color: var(--text);
            font-weight: 700;
        }

        h1 {
            font-size: 34px;
        }

        h2 {
            font-size: 26px;
            margin-bottom: 10px;
        }

        p {
            color: var(--muted);
            line-height: 1.7;
            margin-top: 0;
        }

        .badge {
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(79, 124, 255, 0.12);
            border: 1px solid rgba(122, 162, 255, 0.22);
            color: var(--accent-2);
            font-size: 12px;
            font-weight: 600;
        }

        .panel {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
            margin-top: 18px;
        }

        .panel-title {
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent-2);
            margin-bottom: 8px;
            font-weight: 700;
        }

        .actions {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 18px;
        }

        .btn, .btn-secondary {
            display: inline-block;
            padding: 11px 16px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            transition: 0.18s ease;
        }

        .btn {
            background: var(--accent);
            color: white;
            border: 1px solid transparent;
        }

        .btn:hover {
            background: #638cff;
        }

        .btn-secondary {
            background: transparent;
            color: var(--text);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            border-color: var(--accent);
            color: var(--accent-2);
        }

        .search-box {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 18px;
        }

        input[type="text"] {
            flex: 1 1 320px;
            min-width: 240px;
            padding: 12px 14px;
            border-radius: 10px;
            border: 1px solid var(--border);
            background: #0b1322;
            color: var(--text);
            outline: none;
        }

        input[type="text"]:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(79,124,255,0.15);
        }

        button {
            padding: 12px 16px;
            border: none;
            border-radius: 10px;
            background: var(--accent);
            color: white;
            font-weight: 600;
            cursor: pointer;
        }

        button:hover {
            background: #638cff;
        }

        code, pre {
            font-family: "SFMono-Regular", Consolas, monospace;
        }

        .code-inline {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            color: #d9e5ff;
        }

        pre {
            margin: 0;
            background: #09101d;
            border: 1px solid var(--border);
            padding: 16px;
            border-radius: 12px;
            overflow-x: auto;
            color: #d7e3ff;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .muted-note {
            margin-top: 18px;
            font-size: 12px;
            color: #6d7c98;
        }

        .footer {
            margin-top: 16px;
            text-align: center;
            color: #63718d;
            font-size: 12px;
        }

        .empty {
            color: #8ea0c2;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="shell">
        <div class="card">
            {{ content|safe }}
            <div class="footer">archive-search v2.4 • diagnostics retention enabled</div>
        </div>
    </div>
</body>
</html>
"""


@app.route("/")
def home():
    emit("WEB_REQUEST", path="/", method="GET")
    html = """
    <div class="topbar">
        <div class="brand">
            <small>Internal Archive Service</small>
            <h1>Internal Search Portal</h1>
        </div>
        <div class="badge">Restricted Environment</div>
    </div>

    <p>
        Use the internal archive search endpoint to query indexed records.
        Search activity may be retained for troubleshooting and diagnostics.
    </p>

    <div class="panel">
        <div class="panel-title">Quick Start</div>
        <p>
            Begin with a test query or review the help page for operational notes.
        </p>

        <div class="actions">
            <a class="btn" href="/search?q=test">Run Test Query</a>
            <a class="btn-secondary" href="/help">Open Help</a>
        </div>
    </div>

    <div class="panel">
        <div class="panel-title">Endpoint Reference</div>
        <p><span class="code-inline">/search?q=test</span> Execute a search query against the archive.</p>
        <p><span class="code-inline">/help</span> Read operator notes and troubleshooting guidance.</p>
    </div>

    <div class="muted-note">
        <!-- diagnostic logs remain available to engineering while legacy mode is enabled -->
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/help")
def help_page():
    emit("WEB_REQUEST", path="/help", method="GET")
    html = """
    <h2>Help</h2>
    <p>
        The archive records incoming queries for operational troubleshooting.
        Engineering staff may inspect diagnostic output when investigating search anomalies.
    </p>

    <div class="panel">
        <div class="panel-title">Operational Notes</div>
        <p>1. Every query is recorded for service diagnostics.</p>
        <p>2. Legacy troubleshooting interfaces may remain available in maintenance mode.</p>
        <p>3. Diagnostic output should not be exposed in production-facing deployments.</p>
    </div>

    <div class="actions">
        <a class="btn" href="/search?q=test">Return to Search</a>
        <a class="btn-secondary" href="/">Back to Portal</a>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/search")
def search():
    query = request.args.get("q", "")
    emit("WEB_REQUEST", path="/search", method="GET", query=query)

    LOGS.append(f"{time.time():.0f} QUERY={query}")

    if "flag_probe" in query:
        LOGS.append(f"{time.time():.0f} SECRET={FLAG}")
        emit("FLAG_ATTEMPT", probe="flag_probe")

    html = f"""
    <h2>Search Results</h2>
    <p>Your query has been recorded by the archive service.</p>

    <div class="panel">
        <div class="panel-title">Recorded Query</div>
        <p><span class="code-inline">{query}</span></p>
    </div>

    <div class="panel">
        <div class="panel-title">Result Status</div>
        <p>No direct results were found for this query.</p>
    </div>

    <div class="actions">
        <a class="btn" href="/search?q=test">Try Example Query</a>
        <a class="btn-secondary" href="/help">Read Help</a>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/logs")
def logs():
    emit("WEB_REQUEST", path="/logs", method="GET")

    body = "\n".join(LOGS) if LOGS else "[diagnostics] no records captured yet"

    html = f"""
    <h2>Diagnostics Output</h2>
    <p>
        This page exposes retained search diagnostics for troubleshooting purposes.
    </p>

    <div class="panel">
        <div class="panel-title">Log Stream</div>
        <pre>{body}</pre>
    </div>

    <div class="actions">
        <a class="btn-secondary" href="/">Back to Portal</a>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1337)
