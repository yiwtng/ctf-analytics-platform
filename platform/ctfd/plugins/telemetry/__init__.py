"""
Platform-side telemetry for the learning-analytics study.

WHY THIS EXISTS
The skill engine scores four of its seven dimensions from events that describe
what a learner did in the competition UI -- opening a challenge, unlocking a
hint, submitting a flag and whether it was right, giving up. Nothing emitted
them. The engine, the Grafana dashboards and the design documentation all read
CHALLENGE_OPEN_UI, HINT_UNLOCK_UI, FLAG_SUBMIT_UI and FLAG_SUBMIT_RESULT, but no
component in the deployment produced any of them, so Blue Analysis, Accuracy,
Persistence and Time Efficiency were all computed from zeros and sat at their
baselines. A learner who never submitted a flag scored the same accuracy as one
who submitted correctly every time.

WHY SERVER-SIDE RATHER THAN THEME JAVASCRIPT
Three reasons, in order of importance:

1. Participants cannot forge or suppress these events. The SSH challenge
   necessarily grants shell access and its telemetry is therefore self-reported;
   these events are recorded by the server the participant is talking to, which
   is the strongest position available. For a study whose dependent variable is
   derived from behaviour, that difference matters.
2. The verdict on a submission comes from CTFd's own grader, not from a guess
   about what the UI displayed.
3. It survives a theme change. The active theme here is not the one shipped in
   the repository, and a JavaScript hook attached to a theme would have been lost
   the moment the theme changed -- silently, and mid-study.

DESIGN
Events are emitted from an after_request hook, so no CTFd internals are patched
and no endpoint is wrapped. Emission is best-effort and never raises: telemetry
must not be able to break a submission. Failures are counted and logged rather
than propagated.
"""

import logging
import os
import re
import threading

import requests
from flask import request

log = logging.getLogger("ctfd.telemetry")

# The orchestrator is reached over the container network. This must not be the
# browser-facing public base, which resolves to the reverse proxy and has no
# /event route.
ORCH_EVENT_BASE = (os.getenv("ORCH_EVENT_BASE") or "").strip() or "http://orchestrator:8001"
EVENT_URL = ORCH_EVENT_BASE.rstrip("/") + "/event"

# Short: a slow orchestrator must never delay a learner's page load.
TIMEOUT_SECONDS = float(os.getenv("TELEMETRY_TIMEOUT_SECONDS", "2"))

_ATTEMPT_PATH = "/api/v1/challenges/attempt"
_CHALLENGE_PATH = re.compile(r"^/api/v1/challenges/(\d+)/?$")
_UNLOCK_PATH = "/api/v1/unlocks"


def _slugify_challenge(name):
    """
    Map a CTFd challenge name onto the identifier the skill engine expects.

        "Blue - Misleading Intel"  -> blue_misleading_intel
        "Red - Ghost Login"        -> red_ghost_login
        "Blue - Multi-stage Flag"  -> blue_multi_stage_flag

    The engine partitions challenges into red and blue families by this prefix,
    so a name that does not follow the convention would be scored as neither.
    """
    if not name:
        return None
    slug = str(name).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return re.sub(r"_+", "_", slug).strip("_") or None


def _current_user_key():
    """
    The participant key is the CTFd user id as text: the analysis joins
    user_skill_reports.user_key against experiment_assignment.user_id cast to
    text, so anything else would silently fail to join.
    """
    try:
        from CTFd.utils.user import get_current_user

        user = get_current_user()
        return str(user.id) if user else None
    except Exception:
        return None


def _challenge_name(challenge_id):
    try:
        from CTFd.models import Challenges

        challenge = Challenges.query.filter_by(id=challenge_id).first()
        return challenge.name if challenge else None
    except Exception:
        return None


def _post(params):
    try:
        requests.post(EVENT_URL, params=params, timeout=TIMEOUT_SECONDS)
    except Exception as exc:  # never surface telemetry failure to the learner
        log.warning("telemetry post failed (%s): %s", params.get("event_type"), exc)


def emit(event_type, user_key, challenge_id=None, **payload):
    """Fire and forget. Errors are logged, never raised."""
    if not user_key:
        return
    params = {"event_type": event_type, "user_key": user_key, "source": "ctfd"}
    if challenge_id:
        params["challenge_id"] = challenge_id
    for key, value in payload.items():
        if value is not None:
            params[key] = str(value)
    threading.Thread(target=_post, args=(params,), daemon=True).start()


def load(app):
    @app.after_request
    def _telemetry(response):
        try:
            _record(response)
        except Exception as exc:
            # A bug in telemetry must not turn a working page into a 500.
            log.warning("telemetry hook error: %s", exc)
        return response

    def _record(response):
        path = request.path or ""
        method = request.method

        # ---- challenge opened -------------------------------------------
        match = _CHALLENGE_PATH.match(path)
        if method == "GET" and match and response.status_code == 200:
            challenge_id = int(match.group(1))
            slug = _slugify_challenge(_challenge_name(challenge_id))
            emit(
                "CHALLENGE_OPEN_UI",
                _current_user_key(),
                challenge_id=slug,
                ctfd_challenge_id=challenge_id,
            )
            return

        # ---- flag submitted ---------------------------------------------
        if method == "POST" and path.rstrip("/") == _ATTEMPT_PATH:
            # Read CTFd's verdict first, and emit nothing without one.
            #
            # A request rejected before grading -- CSRF failure, expired session,
            # malformed body -- reaches this hook exactly like a real submission
            # does. Recording it would manufacture a wrong answer the learner
            # never gave: accuracy is scored from the correct-to-incorrect ratio,
            # so a handful of rejected requests would depress the score of a
            # participant who did nothing wrong. Absence of a status is the
            # signal that the submission never reached the grader.
            status = None
            try:
                payload = response.get_json(silent=True) or {}
                status = (payload.get("data") or {}).get("status")
            except Exception:
                status = None

            if not status:
                return

            user_key = _current_user_key()
            body = request.get_json(silent=True) or {}
            ctfd_challenge_id = body.get("challenge_id")
            slug = _slugify_challenge(_challenge_name(ctfd_challenge_id))

            # The attempt itself: what persistence and time-efficiency count.
            emit("FLAG_SUBMIT_UI", user_key, challenge_id=slug,
                 ctfd_challenge_id=ctfd_challenge_id, status=status)

            # Correctness is asserted only for statuses that are actually a
            # grading verdict. "ratelimited" means CTFd declined to grade, and
            # calling that an incorrect answer would be wrong in the same way.
            graded = status in ("correct", "incorrect", "already_solved")

            # The skill engine reads payload["result"] and recognises exactly two
            # values, "submitted" and "wrong"; anything else counts as neither.
            # That vocabulary predates this plugin, so it is emitted alongside the
            # newer fields rather than replacing them -- writing only status and
            # correct left the engine seeing no submissions at all, and accuracy
            # sat at its no-data default of 100 while the learner was submitting
            # wrong answers. "already_solved" deliberately maps to neither: it is
            # not a fresh solve and not a wrong answer.
            result = {"correct": "submitted", "incorrect": "wrong"}.get(status)

            emit(
                "FLAG_SUBMIT_RESULT",
                user_key,
                challenge_id=slug,
                result=result,
                status=status,
                # Both the raw CTFd status and the boolean it reduces to, so a
                # future CTFd release adding a status cannot silently be counted
                # as a wrong answer.
                correct=("true" if status == "correct" else "false") if graded else None,
                graded="true" if graded else "false",
            )
            return

        # ---- hint unlocked ----------------------------------------------
        if method == "POST" and path.rstrip("/") == _UNLOCK_PATH and response.status_code == 200:
            body = request.get_json(silent=True) or {}
            if (body.get("type") or "").lower() == "hints":
                emit("HINT_UNLOCK_UI", _current_user_key(),
                     target=body.get("target"))
            return

    log.info("telemetry plugin loaded; posting to %s", EVENT_URL)
