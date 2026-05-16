import time
from app.feedback.rules import generate_feedback_for_session
from app.db import SessionLocal
from sqlalchemy import text

CHECK_INTERVAL = 30  # วินาที

def get_active_sessions():
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT DISTINCT session_id
            FROM events
            WHERE session_id IS NOT NULL
        """)).fetchall()
        return [r[0] for r in rows]

def already_generated(session_id):
    with SessionLocal() as db:
        row = db.execute(text("""
            SELECT 1 FROM events
            WHERE event_type='FEEDBACK_GENERATED'
            AND session_id=:sid
            LIMIT 1
        """), {"sid": session_id}).fetchone()
        return row is not None

def run():
    while True:
        sessions = get_active_sessions()

        for sid in sessions:
            if not already_generated(sid):
                try:
                    generate_feedback_for_session(sid)
                    print(f"[+] Feedback generated for {sid}")
                except Exception as e:
                    print(f"[!] Error: {e}")

        time.sleep(CHECK_INTERVAL)
