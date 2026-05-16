import os
import requests

ORCH_URL = os.getenv("ORCH_URL")
SESSION_ID = os.getenv("SESSION_ID")
USER_ID = os.getenv("USER_ID")
CHALLENGE_ID = os.getenv("CHALLENGE_ID")

def send_event(event_type: str, extra: dict | None = None) -> None:
    if not ORCH_URL:
        return

    params = {
        "event_type": event_type,
        "user_key": USER_ID,
        "challenge_id": CHALLENGE_ID,
        "session_id": SESSION_ID,
    }
    if extra:
        for k, v in extra.items():
            params[k] = str(v)

    try:
        requests.post(ORCH_URL, params=params, timeout=0.5)
    except Exception:
        pass
