from flask import Flask, request, jsonify, render_template_string
from event_client import send_event

app = Flask(__name__)

FLAG = "flag{d45179d1b1562e1f334dcba5e88e9199}"
TOKENS = {"ops-user": "OPS-TOKEN-7788"}

# -------------------------
# GLOBAL LOG
# -------------------------
@app.before_request
def log_req():
    send_event("WEB_REQUEST", {
        "path": request.path,
        "method": request.method
    })


# -------------------------
# HTML TEMPLATE (THEME)
# -------------------------
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Ghost Login</title>
    <style>
        body {
            background: #0d1117;
            color: #c9d1d9;
            font-family: 'Segoe UI', sans-serif;
            margin: 0;
        }

        .container {
            max-width: 700px;
            margin: 80px auto;
            background: #161b22;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
        }

        h1 {
            color: #58a6ff;
            margin-bottom: 10px;
        }

        p {
            color: #8b949e;
        }

        a {
            color: #58a6ff;
            text-decoration: none;
        }

        input {
            width: 100%;
            padding: 10px;
            margin-top: 10px;
            background: #0d1117;
            border: 1px solid #30363d;
            color: #c9d1d9;
            border-radius: 6px;
        }

        button {
            margin-top: 15px;
            padding: 10px;
            width: 100%;
            background: #238636;
            border: none;
            color: white;
            border-radius: 6px;
            cursor: pointer;
        }

        .hint {
            margin-top: 20px;
            font-size: 12px;
            color: #6e7681;
        }

        .footer {
            margin-top: 30px;
            font-size: 11px;
            color: #484f58;
            text-align: center;
        }
    </style>
</head>
<body>

<div class="container">
    {{ content|safe }}

    <div class="footer">
        ghost-auth v1.1 • internal use only
    </div>
</div>

</body>
</html>
"""


# -------------------------
# INDEX
# -------------------------
@app.route("/")
def index():
    html = """
    <h1>👻 Ghost Login</h1>
    <p>Try the login page. Not everything is what it seems.</p>

    <ul>
        <li><a href="/login">Login Portal</a></li>
        <li><a href="/docs">API Documentation</a></li>
    </ul>

    <div class="hint">
        <!-- legacy system still exposes internal auth paths -->
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


# -------------------------
# DOCS
# -------------------------
@app.route("/docs")
def docs():
    return {
        "service": "ghost-login",
        "version": "1.1",
        "notes": "legacy endpoints removed, token middleware still active"
    }


# -------------------------
# LOGIN PAGE
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        html = """
        <h1>Login</h1>
        <p>Authorized personnel only</p>

        <form method="POST">
            <input name="username" placeholder="Username">
            <input name="password" type="password" placeholder="Password">
            <button type="submit">Sign in</button>
        </form>

        <div class="hint">
            <!-- old ops interface might still be reachable -->
        </div>
        """
        return render_template_string(BASE_HTML, content=html)

    username = request.values.get("username", "")
    password = request.values.get("password", "")

    # detect probing
    if any(x in (username + password).lower() for x in [" or ", "'", "--", "union"]):
        send_event("WEB_PROBE", {"kind": "sqli_like"})
        return jsonify({"status": "blocked", "message": "suspicious input"}), 403

    # honeypot
    if username == "admin" and password == "admin":
        send_event("LOGIN_FAIL", {"reason": "honeypot"})
        return jsonify({"status": "fail", "message": "invalid credentials"}), 401

    return jsonify({"status": "fail"}), 401


# -------------------------
# REAL VULNERABLE ENDPOINT
# -------------------------
@app.route("/api/auth/token")
def api_auth_token():
    token = request.headers.get("X-OPS-TOKEN", "")

    if token == TOKENS["ops-user"]:
        send_event("SUBMIT_FLAG", {
            "correct": True,
            "route": "/api/auth/token"
        })
        return jsonify({
            "status": "ok",
            "flag": FLAG
        })

    send_event("API_AUTH_FAIL")
    return jsonify({"status": "denied"}), 403


# -------------------------
# HEALTH
# -------------------------
@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)