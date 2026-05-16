from sqlalchemy import text
from app.db import SessionLocal
import json



def write_event(
    event_type: str,
    user_key: str = None,
    team_key: str = None,
    challenge_id: str = None,
    session_id: str = None,
    source: str = "orchestrator",
    payload: dict = None
):
    payload = payload or {}

    with SessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO events (
                    user_key, team_key, challenge_id, session_id,
                    event_type, source, payload
                ) VALUES (
                    :user_key, :team_key, :challenge_id, :session_id,
                    :event_type, :source, CAST(:payload AS jsonb)
                )
            """),
            {
                "user_key": user_key,
                "team_key": team_key,
                "challenge_id": challenge_id,
                "session_id": session_id,
                "event_type": event_type,
                "source": source,
                "payload": json.dumps(payload)
            }
        )
        db.commit()


def write_feedback(
    user_key: str,
    challenge_id: str,
    session_id: str,
    feedback_type: str,
    severity: str,
    feedback_text: str,
    feedback_json: dict = None
):
    feedback_json = feedback_json or {}

    with SessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO feedback_reports (
                    user_key, challenge_id, session_id,
                    feedback_type, severity, feedback_text, feedback_json
                ) VALUES (
                    :user_key, :challenge_id, :session_id,
                    :feedback_type, :severity, :feedback_text, CAST(:feedback_json AS jsonb)
                )
            """),
            {
                "user_key": user_key,
                "challenge_id": challenge_id,
                "session_id": session_id,
                "feedback_type": feedback_type,
                "severity": severity,
                "feedback_text": feedback_text,
                "feedback_json": json.dumps(feedback_json)
            }
        )
        db.commit()

def write_participant_feedback(
    user_key: str,
    usability_score: int,
    challenge_quality_score: int,
    recommendation_quality_score: int,
    confidence_improvement_score: int,
    favorite_part: str = None,
    improvement_point: str = None,
    comments: str = None
):
    with SessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO participant_feedback (
                    user_key,
                    usability_score,
                    challenge_quality_score,
                    recommendation_quality_score,
                    confidence_improvement_score,
                    favorite_part,
                    improvement_point,
                    comments
                ) VALUES (
                    :user_key,
                    :usability_score,
                    :challenge_quality_score,
                    :recommendation_quality_score,
                    :confidence_improvement_score,
                    :favorite_part,
                    :improvement_point,
                    :comments
                )
            """),
            {
                "user_key": user_key,
                "usability_score": usability_score,
                "challenge_quality_score": challenge_quality_score,
                "recommendation_quality_score": recommendation_quality_score,
                "confidence_improvement_score": confidence_improvement_score,
                "favorite_part": favorite_part,
                "improvement_point": improvement_point,
                "comments": comments
            }
        )
        db.commit()


def get_latest_participant_feedback(user_key: str):
    with SessionLocal() as db:
        row = db.execute(
            text("""
                SELECT
                    user_key,
                    usability_score,
                    challenge_quality_score,
                    recommendation_quality_score,
                    confidence_improvement_score,
                    favorite_part,
                    improvement_point,
                    comments,
                    ts
                FROM participant_feedback
                WHERE user_key = :user_key
                ORDER BY ts DESC
                LIMIT 1
            """),
            {"user_key": user_key}
        ).mappings().first()

        return dict(row) if row else None

def write_ai_report(
    user_key: str,
    model_name: str,
    raw_summary: dict,
    ai_report: dict
):
    with SessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO user_ai_reports (
                    user_key,
                    model,
                    profile,
                    strengths,
                    weaknesses,
                    recommendations,
                    summary,
                    confidence,
                    raw_response
                ) VALUES (
                    :user_key,
                    :model_name,
                    CAST(:profile AS JSONB),
                    CAST(:strengths AS JSONB),
                    CAST(:weaknesses AS JSONB),
                    CAST(:recommendations AS JSONB),
                    :summary,
                    :confidence,
                    CAST(:raw_response AS JSONB)
                )
            """),
            {
                "user_key": user_key,
                "model_name": model_name,
                "profile": json.dumps(ai_report.get("profile", [])),
                "strengths": json.dumps(ai_report.get("strengths", [])),
                "weaknesses": json.dumps(ai_report.get("weaknesses", [])),
                "recommendations": json.dumps(ai_report.get("recommendations", [])),
                "summary": ai_report.get("summary"),
                "confidence": ai_report.get("confidence"),
                "raw_response": json.dumps({
                    "raw_summary": raw_summary,
                    "ai_report": ai_report,
                }),
            }
        )
        db.commit()


def get_latest_ai_report(user_key: str):
    with SessionLocal() as db:
        row = db.execute(
            text("""
                SELECT
                    user_key,
                    model,
                    profile,
                    strengths,
                    weaknesses,
                    recommendations,
                    summary,
                    confidence,
                    raw_response,
                    generated_at
                FROM user_ai_reports
                WHERE user_key = :user_key
                ORDER BY generated_at DESC
                LIMIT 1
            """),
            {"user_key": user_key}
        ).mappings().first()

        if not row:
            return None

        raw_response = row["raw_response"] or {}
        ai_report = raw_response.get("ai_report") or {
            "profile": row["profile"],
            "strengths": row["strengths"],
            "weaknesses": row["weaknesses"],
            "recommendations": row["recommendations"],
            "summary": row["summary"],
            "confidence": row["confidence"],
        }

        return {
            "user_key": row["user_key"],
            "model_name": row["model"],
            "raw_summary": raw_response.get("raw_summary"),
            "ai_report": ai_report,
            "ts": row["generated_at"],
        }





def get_all_participant_feedback():
    with SessionLocal() as db:
        result = db.execute(
            text("""
                SELECT
                    feedback_id,
                    ts,
                    user_key,
                    usability_score,
                    challenge_quality_score,
                    recommendation_quality_score,
                    confidence_improvement_score,
                    favorite_part,
                    improvement_point,
                    comments
                FROM participant_feedback
                ORDER BY ts DESC
            """)
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
