import logging
import os
import time

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

audit_log = logging.getLogger("audit")
logging.basicConfig(level=logging.INFO)
_audit_handler = logging.FileHandler("/tmp/audit.log")
_audit_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
audit_log.addHandler(_audit_handler)

limiter = Limiter(key_func=get_remote_address)

from app.experiment import is_treatment, assignment_summary

from app.session_manager import start_session, stop_session
from app.feedback.rules import generate_feedback_for_session, generate_feedback_for_user
from app.events import (
    write_event,
    write_participant_feedback,
    get_latest_participant_feedback,
    get_latest_ai_report,
    get_all_participant_feedback,
)
from app.feedback.gemini_analyzer import (
    analyze_user_with_gemini,
    analyze_and_save_user_with_gemini,
)
from app.report_service import (
    generate_user_report,
    generate_all_reports,
    get_latest_user_report,
    get_all_users_with_events,
    get_round_comparison_all,
    get_round_comparison_participant,
)

# =========================
# INIT
# =========================
app = FastAPI(title="CTF Orchestrator")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins_env = os.getenv("ORCH_CORS_ORIGINS", "").strip()
if _cors_origins_env:
    _allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="app/templates")


# =========================
# MODELS
# =========================
class ParticipantFeedbackInput(BaseModel):
    user_key: str
    usability_score: int = Field(ge=1, le=5)
    challenge_quality_score: int = Field(ge=1, le=5)
    recommendation_quality_score: int = Field(ge=1, le=5)
    confidence_improvement_score: int = Field(ge=1, le=5)
    favorite_part: str | None = None
    improvement_point: str | None = None
    comments: str | None = None


# =========================
# BASIC ROUTES
# =========================
@app.get("/")
def read_root():
    return {"status": "ok", "service": "orchestrator"}


@app.get("/health")
def health():
    return {"status": "healthy"}


# =========================
# SESSION
# =========================
@app.get("/start")
def start(user: str = Query(...), challenge: str = Query(...)):
    return start_session(user, challenge)


@app.get("/stop")
def stop(session_id: str = Query(...)):
    return stop_session(session_id)


# =========================
# EVENTS
# =========================
@app.post("/event")
def create_event(
    request: Request,
    event_type: str = Query(...),
    user_key: str | None = Query(None),
    challenge_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    reserved_keys = {"event_type", "user_key", "challenge_id", "session_id"}
    payload = {}
    for key, value in request.query_params.multi_items():
        if key not in reserved_keys:
            payload[key] = value

    write_event(
        event_type=event_type,
        user_key=user_key,
        challenge_id=challenge_id,
        session_id=session_id,
        source="api",
        payload=payload,
    )
    return {"status": "ok"}


@app.post("/event_json")
async def collect_event_json(req: Request):
    body = await req.json()

    write_event(
        event_type=body.get("event_type"),
        user_key=body.get("user_key"),
        challenge_id=body.get("challenge_id"),
        session_id=body.get("session_id"),
        source="api_json",
        payload=body.get("payload", {}),
    )
    return {"status": "ok"}


# =========================
# FEEDBACK
# =========================
@app.get("/feedback")
def feedback(session_id: str = Query(...)):
    return generate_feedback_for_session(session_id)


@app.get("/analyze_user")
def analyze_user(user: str = Query(...)):
    return generate_feedback_for_user(user)


@app.post("/participant_feedback")
def participant_feedback(data: ParticipantFeedbackInput):
    write_participant_feedback(
        user_key=data.user_key,
        usability_score=data.usability_score,
        challenge_quality_score=data.challenge_quality_score,
        recommendation_quality_score=data.recommendation_quality_score,
        confidence_improvement_score=data.confidence_improvement_score,
        favorite_part=data.favorite_part,
        improvement_point=data.improvement_point,
        comments=data.comments,
    )
    return {"status": "ok"}


# =========================
# FEEDBACK LIST API (ADMIN)
# =========================
@app.get("/feedback/list")
def feedback_list():
    return {
        "status": "ok",
        "results": get_all_participant_feedback()
    }


@app.get("/feedback/list/{user_key}")
def feedback_list_by_user(user_key: str):
    all_rows = get_all_participant_feedback()
    filtered = [row for row in all_rows if row.get("user_key") == user_key]
    return {
        "status": "ok",
        "results": filtered
    }



# =========================
# AI
# =========================
@app.get("/analyze_user_ai")
def analyze_user_ai(user: str = Query(...)):
    return analyze_user_with_gemini(user)


@app.get("/analyze_user_ai_save")
def analyze_user_ai_save(user: str = Query(...)):
    return analyze_and_save_user_with_gemini(user)


# =========================
# HTML PAGE (USER REPORT)
# =========================
@app.get("/report", response_class=HTMLResponse)
@limiter.limit("30/minute")
def report_page(request: Request, user: str = Query(...), user_id: int | None = Query(None)):
    """
    Personal report page. AI feedback section is only shown to TREATMENT
    participants. Control participants see skill scores only.
    Pass `user_id` (CTFd integer user ID) to apply experiment gating.
    """
    show_ai_section = (user_id is None) or is_treatment(user_id)

    cached = get_latest_ai_report(user) if show_ai_section else None
    survey = get_latest_participant_feedback(user)

    if show_ai_section:
        if cached:
            ai_result = {
                "status": "ok",
                "user_key": cached["user_key"],
                "raw_summary": cached["raw_summary"],
                "ai_report": cached["ai_report"],
                "model": cached["model_name"],
                "ts": cached["ts"],
            }
        else:
            ai_result = analyze_user_with_gemini(user)
    else:
        ai_result = None  # control group: no AI feedback

    audit_log.info("REPORT_VIEW user_key=%s user_id=%s ip=%s", user, user_id, request.client.host if request.client else "unknown")
    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={
            "user_key": user,
            "ai_result": ai_result,
            "show_ai_section": show_ai_section,
            "survey": survey,
        }
    )


# =========================
# EXPERIMENT (ADMIN)
# =========================
@app.get("/admin-experiment-summary")
@limiter.limit("20/minute")
def experiment_summary(request: Request):
    """Return current control/treatment allocation balance."""
    audit_log.info("ADMIN_EXPERIMENT_SUMMARY ip=%s", request.client.host if request.client else "unknown")
    try:
        return {"status": "ok", "summary": assignment_summary()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# =========================
# REPORT API
# =========================
@app.post("/generate_report/{user_key}")
@limiter.limit("10/minute")
def generate_report(request: Request, user_key: str):
    audit_log.info("GENERATE_REPORT user_key=%s ip=%s", user_key, request.client.host if request.client else "unknown")
    return generate_user_report(user_key)


@app.post("/generate_report_all")
@limiter.limit("5/minute")
def generate_report_all_api(request: Request):
    audit_log.info("GENERATE_REPORT_ALL ip=%s", request.client.host if request.client else "unknown")
    return generate_all_reports()


@app.get("/report/{user_key}")
def get_report(user_key: str):
    result = get_latest_user_report(user_key)
    if not result["skill_report"]:
        raise HTTPException(status_code=404, detail="report not found")
    return result


# =========================
# ADMIN REPORT ALL
# =========================
@app.get("/report_all")
def get_report_all():
    users = get_all_users_with_events()
    reports = []

    for user_key in users:
        try:
            result = get_latest_user_report(user_key)

            if result.get("skill_report"):
                reports.append(result)
            else:
                reports.append({
                    "status": "empty",
                    "user_key": user_key,
                    "skill_report": None,
                    "ai_report": None,
                })

        except Exception as exc:
            reports.append({
                "status": "error",
                "user_key": user_key,
                "error": str(exc),
            })

    return {
        "status": "ok",
        "count": len(reports),
        "reports": reports,
    }


@app.get("/round_comparison_all")
def round_comparison_all():
    return get_round_comparison_all()


@app.get("/round_comparison/{participant_id}")
def round_comparison_participant(participant_id: str):
    result = get_round_comparison_participant(participant_id)
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail=result.get("message", "participant not found"))
    return result


# =========================
# VALIDATION (ADMIN)
# =========================
class ExpertRatingInput(BaseModel):
    rater_id: str
    participant_code: str
    round_no: int
    dimension: str
    score: float = Field(ge=0, le=100)


@app.get("/admin-validation")
def admin_validation():
    """Return ICC, Cronbach's alpha, and convergent validity for all dimensions."""
    from app.validation_service import (
        compute_icc, compute_cronbach_alpha, compute_convergent_validity, DIMENSIONS
    )
    icc_results = {dim: compute_icc(dim) for dim in DIMENSIONS}
    return {
        "status": "ok",
        "icc_per_dimension": icc_results,
        "cronbach_alpha": compute_cronbach_alpha(),
        "convergent_validity_solve_count": compute_convergent_validity("solve_count"),
    }


@app.post("/admin-validation/expert-rating")
def submit_expert_rating(data: ExpertRatingInput):
    """Accept a single expert rating for a participant/dimension."""
    from app.validation_service import store_expert_rating, ExpertRating
    try:
        store_expert_rating(ExpertRating(
            rater_id=data.rater_id,
            participant_code=data.participant_code,
            round_no=data.round_no,
            dimension=data.dimension,
            score=data.score,
        ))
        return {"status": "ok"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# =========================
# SURVEY PAGE
# =========================
@app.get("/survey", response_class=HTMLResponse)
def survey_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="survey.html",
        context={}
    )
