from sqlalchemy import text
from app.db import SessionLocal
from app.events import write_feedback, write_event
from collections import Counter

def _fetch_events(session_id: str):
    with SessionLocal() as db:
        rows = db.execute(
            text("""
                SELECT ts, user_key, challenge_id, event_type, payload
                FROM events
                WHERE session_id = :session_id
                ORDER BY ts ASC
            """),
            {"session_id": session_id}
        ).mappings().all()
        return rows


def generate_feedback_for_session(session_id: str):
    rows = _fetch_events(session_id)
    if not rows:
        return {"status": "error", "message": "no events found"}

    user_key = rows[0]["user_key"]
    challenge_id = rows[0]["challenge_id"]

    event_types = [r["event_type"] for r in rows]
    feedback_items = []

    # ---------- Generic counters ----------
    web_requests = sum(1 for r in rows if r["event_type"] == "WEB_REQUEST")
    web_probes = sum(1 for r in rows if r["event_type"] == "WEB_PROBE")
    login_fail = sum(1 for r in rows if r["event_type"] == "LOGIN_FAIL")
    api_auth_fail = sum(1 for r in rows if r["event_type"] == "API_AUTH_FAIL")
    submit_count = sum(1 for r in rows if r["event_type"] == "SUBMIT_FLAG")

    tcp_connect = sum(1 for r in rows if r["event_type"] == "TCP_CONNECT")
    tcp_input = sum(1 for r in rows if r["event_type"] == "TCP_INPUT")
    tcp_bad_auth = sum(1 for r in rows if r["event_type"] == "TCP_BAD_AUTH")
    tcp_hello_ok = sum(1 for r in rows if r["event_type"] == "TCP_HELLO_OK")
    flag_found = sum(1 for r in rows if r["event_type"] == "FLAG_FOUND")

    ssh_commands = [r for r in rows if r["event_type"] == "SSH_COMMAND"]
    ssh_flag_attempts = sum(1 for r in rows if r["event_type"] == "SSH_FLAG_ATTEMPT")

    # ---------- RED: Ghost Login ----------
    if challenge_id == "red_ghost_login":
        if login_fail >= 3 and api_auth_fail == 0:
            feedback_items.append({
                "feedback_type": "decoy_trap",
                "severity": "high",
                "text": "คุณใช้เวลาอยู่กับหน้า login มากเกินไปและยังไม่เห็นการไปแตะ API จริง แนะนำให้ทำ recon จาก /docs หรือ endpoint อื่นก่อน brute-force"
            })

        if web_probes >= 3:
            feedback_items.append({
                "feedback_type": "probe_heavy",
                "severity": "medium",
                "text": "คุณลอง payload เชิงโจมตีหลายครั้งติดกัน ควรสลับไปอ่าน behavior ของระบบหรือดู documentation ก่อน"
            })

        if web_requests >= 5 and submit_count == 0:
            feedback_items.append({
                "feedback_type": "stuck_recon",
                "severity": "low",
                "text": "คุณมี interaction กับเว็บหลายครั้งแต่ยังไม่ถึงจุด solve ชัดเจน อาจต้อง map flow ของระบบก่อนเลือกจุดโจมตี"
            })

    # ---------- RED: Protocol Probe ----------
    if challenge_id == "red_protocol_probe":
        if tcp_connect >= 1 and tcp_hello_ok == 0:
            feedback_items.append({
                "feedback_type": "protocol_misunderstanding",
                "severity": "high",
                "text": "คุณเชื่อมต่อได้แล้วแต่ยังไม่ผ่านขั้นตอน HELLO แสดงว่ายังไม่เข้าใจ protocol flow เริ่มจากการอ่าน banner และตอบตามลำดับที่ service ขอ"
            })

        if tcp_hello_ok >= 1 and tcp_bad_auth >= 2:
            feedback_items.append({
                "feedback_type": "guessing_token",
                "severity": "medium",
                "text": "คุณเข้าใจ protocol แล้ว แต่ยังเดา token แบบลองผิดหลายครั้ง ควรหาความหมายของ token จาก context มากกว่าทดลองสุ่ม"
            })

        if tcp_hello_ok >= 1 and tcp_bad_auth == 1 and flag_found >= 1:
            feedback_items.append({
                "feedback_type": "good_recovery",
                "severity": "info",
                "text": "คุณเข้าใจ protocol ได้ดีและ recover จากการลองผิดเพียงครั้งเดียว ถือว่าเป็นรูปแบบการแก้แบบมีเหตุผล"
            })

        if flag_found >= 1 and tcp_input <= 3:
            feedback_items.append({
                "feedback_type": "efficient_protocol_solving",
                "severity": "info",
                "text": "คุณใช้จำนวน interaction น้อยและเข้าถึงคำตอบได้เร็ว แสดงถึงความเข้าใจ flow ของ protocol ในระดับดี"
            })

    # ---------- RED: Pivot Notes ----------
    if challenge_id == "red_pivot_notes":
        cmd_list = []
        for r in ssh_commands:
            payload = r["payload"]
            if isinstance(payload, dict):
                cmd = payload.get("cmd", "")
                if cmd:
                    cmd_list.append(cmd)

        exploration_cmds = {"pwd", "ls", "ls -la", "whoami", "id", "find", "cat"}
        exploration_hits = sum(
            1 for c in cmd_list
            if any(c == x or c.startswith(x + " ") for x in exploration_cmds)
        )

        if len(cmd_list) <= 2 and ssh_flag_attempts >= 1:
            feedback_items.append({
                "feedback_type": "direct_solve_behavior",
                "severity": "info",
                "text": "คุณเข้าถึง flag ได้ด้วยคำสั่งจำนวนน้อยมาก แสดงถึง direct-path behavior มากกว่าการสำรวจระบบ"
            })

        if exploration_hits >= 2 and ssh_flag_attempts >= 1:
            feedback_items.append({
                "feedback_type": "exploratory_behavior",
                "severity": "info",
                "text": "คุณสำรวจ environment ก่อนเข้าถึง flag เป็นลักษณะการแก้ปัญหาแบบเป็นขั้นตอนและมีระบบ"
            })

        if len(cmd_list) >= 5 and ssh_flag_attempts == 0:
            feedback_items.append({
                "feedback_type": "noisy_enumeration",
                "severity": "medium",
                "text": "คุณใช้คำสั่งหลายครั้งแต่ยังไม่เข้าใกล้เป้าหมายชัดเจน ควรตั้งสมมติฐานก่อนสำรวจเพิ่มเติม"
            })

    # ---------- fallback ----------
    if not feedback_items:
        feedback_items.append({
            "feedback_type": "general",
            "severity": "info",
            "text": "ยังไม่มี pattern เด่นชัดจาก session นี้ แต่ event ถูกเก็บครบและพร้อมสำหรับการวิเคราะห์ในระดับละเอียดขึ้น"
        })

    # save feedback
    for item in feedback_items:
        write_feedback(
            user_key=user_key,
            challenge_id=challenge_id,
            session_id=session_id,
            feedback_type=item["feedback_type"],
            severity=item["severity"],
            feedback_text=item["text"],
            feedback_json={"session_id": session_id}
        )

    write_event(
        event_type="FEEDBACK_GENERATED",
        user_key=user_key,
        challenge_id=challenge_id,
        session_id=session_id,
        payload={"feedback_count": len(feedback_items)}
    )

    return {
        "status": "ok",
        "session_id": session_id,
        "user_key": user_key,
        "challenge_id": challenge_id,
        "feedback": feedback_items
    }


def generate_feedback_for_user(user_key: str):
    with SessionLocal() as db:
        sessions = db.execute(
            text("""
                SELECT DISTINCT session_id, challenge_id
                FROM events
                WHERE user_key = :user_key
            """),
            {"user_key": user_key}
        ).mappings().all()

    results = []

    for s in sessions:
        res = generate_feedback_for_session(s["session_id"])
        results.append(res)

    return {
        "status": "ok",
        "user": user_key,
        "total_sessions": len(results),
        "results": results
    }

def generate_user_summary(user_key: str):
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT event_type, COUNT(*) as cnt
            FROM events
            WHERE user_key = :user_key
            GROUP BY event_type
        """), {"user_key": user_key}).mappings().all()

    stats = {r["event_type"]: r["cnt"] for r in rows}

    profile = []

    if stats.get("TCP_BAD_AUTH", 0) > 3:
        profile.append("Brute-force tendency")

    if stats.get("WEB_PROBE", 0) > 5:
        profile.append("Aggressive probing")

    if stats.get("SSH_COMMAND", 0) < 3:
        profile.append("Direct solve behavior")

    return profile


def generate_feedback_for_user(user_key: str):
    with SessionLocal() as db:
        sessions = db.execute(
            text("""
                SELECT DISTINCT session_id, challenge_id
                FROM events
                WHERE user_key = :user_key
                  AND session_id IS NOT NULL
                ORDER BY session_id
            """),
            {"user_key": user_key}
        ).mappings().all()

    session_reports = []
    profile_counter = Counter()

    for s in sessions:
        result = generate_feedback_for_session(s["session_id"])
        if result.get("status") == "ok":
            session_reports.append(result)

            for item in result.get("feedback", []):
                profile_counter[item["feedback_type"]] += 1

    profile = []
    recommendations = []

    if profile_counter["decoy_trap"] >= 1:
        profile.append("มีแนวโน้มติดกับดักหรือจุดหลอก")
        recommendations.append("ฝึก recon และอ่าน behavior ของระบบก่อนเริ่มโจมตี")

    if profile_counter["guessing_token"] >= 1:
        profile.append("มีแนวโน้มลองผิดแบบเดาสุ่มในโจทย์ protocol")
        recommendations.append("ฝึกวิเคราะห์ protocol flow ก่อนทดลอง token หลายแบบ")

    if profile_counter["exploratory_behavior"] >= 1:
        profile.append("มีรูปแบบการแก้แบบสำรวจอย่างเป็นระบบ")
        recommendations.append("รักษาวิธีคิดแบบ step-by-step และต่อยอดด้วยการตั้งสมมติฐานให้เร็วขึ้น")

    if profile_counter["direct_solve_behavior"] >= 1:
        profile.append("มีแนวโน้มแก้แบบ direct path")
        recommendations.append("ลองเพิ่มการสำรวจก่อน solve เพื่อเก็บบริบทและลดความเสี่ยงพลาดจุดสำคัญ")

    if profile_counter["efficient_protocol_solving"] >= 1:
        profile.append("เข้าใจโจทย์ protocol ได้ค่อนข้างเร็ว")
        recommendations.append("ต่อยอดด้วยโจทย์ protocol ที่ซับซ้อนขึ้นและมีหลาย state")

    if not profile:
        profile.append("ยังไม่พบรูปแบบเด่นชัด")
        recommendations.append("ควรเก็บ session เพิ่มเพื่อให้วิเคราะห์ pattern ได้ชัดเจนขึ้น")

    return {
        "status": "ok",
        "user_key": user_key,
        "total_sessions": len(session_reports),
        "profile": profile,
        "recommendations": recommendations,
        "session_reports": session_reports
    }
