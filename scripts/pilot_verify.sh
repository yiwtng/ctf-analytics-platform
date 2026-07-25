#!/usr/bin/env bash
# Pilot verification — run on the production host BEFORE enrolling real participants.
#
# Checks that the full pipeline works end to end. Every check that can be automated is
# automated; the ones that genuinely need a human are listed at the end rather than
# silently skipped.
#
# Non-destructive: the only write is inside a transaction that is rolled back.
#
#   Usage:  bash scripts/pilot_verify.sh [PILOT_USER_KEY]
#           PILOT_USER_KEY defaults to the most recent user_key seen in events.
#
# Exit code 0 = every automated check passed.

set -uo pipefail

DB_C="${DB_CONTAINER:-analytics_db_prod}"
DB_U="${DB_USER:-analytics}"
DB_N="${DB_NAME:-analytics_prod}"
ORCH_C="${ORCH_CONTAINER:-orchestrator_prod}"
REPO="${REPO_DIR:-$HOME/ctf-analytics-platform}"

PASS=0; FAIL=0; WARN=0

# Colour only when writing to a terminal, so a redirected log stays readable.
if [ -t 1 ]; then
  C_G=$'\033[32m'; C_R=$'\033[31m'; C_Y=$'\033[33m'; C_B=$'\033[1m'; C_0=$'\033[0m'
else
  C_G=''; C_R=''; C_Y=''; C_B=''; C_0=''
fi

q()  { docker exec "$DB_C" psql -U "$DB_U" -d "$DB_N" -t -A -c "$1" 2>&1; }
ok()   { printf '  %s✓ PASS%s  %s\n' "$C_G" "$C_0" "$1"; PASS=$((PASS+1)); }
bad()  { printf '  %s✗ FAIL%s  %s\n' "$C_R" "$C_0" "$1"; [ -n "${2:-}" ] && printf '           %s\n' "$2"; FAIL=$((FAIL+1)); }
warn() { printf '  %s! WARN%s  %s\n' "$C_Y" "$C_0" "$1"; [ -n "${2:-}" ] && printf '           %s\n' "$2"; WARN=$((WARN+1)); }
hdr()  { printf '\n%s%s%s\n' "$C_B" "$1" "$C_0"; }

USER_KEY="${1:-}"

echo "==============================================================="
echo " Pilot verification — $(date '+%Y-%m-%d %H:%M:%S')"
echo "==============================================================="

# ---------------------------------------------------------------- infrastructure
hdr "1. Infrastructure"

running=$(docker ps --format '{{.Names}}' | grep -c '_prod$')
[ "$running" -ge 7 ] && ok "containers running ($running)" \
                     || bad "expected 7 *_prod containers, found $running" "docker ps"

unhealthy=$(docker ps --format '{{.Names}} {{.Status}}' | grep -v healthy | grep '_prod' || true)
[ -z "$unhealthy" ] && ok "all containers healthy" || bad "unhealthy containers" "$unhealthy"

code=$(docker exec "$ORCH_C" python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8001/docs',timeout=5).status)" 2>/dev/null)
[ "$code" = "200" ] && ok "orchestrator responds (HTTP 200)" || bad "orchestrator not responding" "got: ${code:-none}"

# ---------------------------------------------------------------- schema
hdr "2. Schema (migrations 010–012)"

chk_col() {  # table, column, label
  local n; n=$(q "SELECT count(*) FROM information_schema.columns WHERE table_name='$1' AND column_name='$2';")
  [ "$n" = "1" ] && ok "$3" || bad "$3" "missing column $1.$2 — migration not applied"
}
chk_col user_skill_reports round_no      "user_skill_reports.round_no (011)"
chk_col user_skill_reports overall_level "user_skill_reports.overall_level (011)"
chk_col user_skill_reports summary_json  "user_skill_reports.summary_json (011)"
chk_col feedback_rating   feedback_source "feedback_rating.feedback_source (010)"
chk_col feedback_rating   comment         "feedback_rating.comment (010)"
chk_col user_ai_reports   report_role     "user_ai_reports.report_role (012)"
chk_col user_ai_reports   round_no        "user_ai_reports.round_no (012)"

uniq=$(q "SELECT count(*) FROM pg_constraint WHERE conrelid='feedback_rating'::regclass AND contype='u';")
[ "$uniq" -ge 1 ] && ok "feedback_rating has a unique key (ON CONFLICT works)" \
                  || bad "feedback_rating has no unique key" "store_feedback_rating() will error"

# ---------------------------------------------------------------- study config
hdr "3. Study configuration"

sr=$(docker exec "$ORCH_C" printenv STUDY_ROUND 2>/dev/null || true)
if [ -z "$sr" ]; then
  bad "STUDY_ROUND is not set" "reports will be stored with round_no NULL and excluded from H1"
elif [[ "$sr" =~ ^[123]$ ]]; then
  ok "STUDY_ROUND = $sr"
else
  bad "STUDY_ROUND = '$sr' is invalid" "must be 1, 2 or 3"
fi

sh=$(docker exec "$ORCH_C" python -c "from app.report_service import GENERATE_SHADOW_REPORTS as g;print(g)" 2>/dev/null)
[ "$sh" = "True" ] && ok "shadow report generation enabled (RQ4)" \
                   || bad "GENERATE_SHADOW_REPORTS is off" "RQ4 within-subject comparison will have no data"

# ---------------------------------------------------------------- pipeline data
hdr "4. Pipeline produced data"

if [ -z "$USER_KEY" ]; then
  USER_KEY=$(q "SELECT user_key FROM events ORDER BY ts DESC LIMIT 1;")
fi
if [ -z "$USER_KEY" ]; then
  bad "no events at all" "play through the challenges first, then re-run"
  echo; echo "Stopping: nothing to verify downstream."; exit 1
fi
echo "  (pilot user_key = $USER_KEY)"

n_ev=$(q "SELECT count(*) FROM events WHERE user_key='$USER_KEY';")
[ "$n_ev" -gt 0 ] && ok "events captured ($n_ev)" || bad "no events for $USER_KEY"

for t in WEB_REQUEST FLAG_SUBMIT_RESULT; do
  c=$(q "SELECT count(*) FROM events WHERE user_key='$USER_KEY' AND event_type='$t';")
  [ "$c" -gt 0 ] && ok "event type $t present ($c)" \
                 || warn "no $t events" "expected if the pilot skipped that challenge type"
done

n_sk=$(q "SELECT count(*) FROM user_skill_reports WHERE user_key='$USER_KEY';")
[ "$n_sk" -gt 0 ] && ok "skill report saved ($n_sk)" \
                  || bad "no skill report" "save_skill_report() failed — check orchestrator logs"

nulls=$(q "SELECT count(*) FROM user_skill_reports WHERE user_key='$USER_KEY' AND (round_no IS NULL OR overall_level IS NULL);")
[ "$nulls" = "0" ] && ok "skill reports have round_no and overall_level" \
                   || bad "$nulls skill report(s) missing round_no/overall_level" "STUDY_ROUND unset when generated?"

# ---------------------------------------------------------------- RQ4 pairing
hdr "5. Dual report (RQ4 within-subject)"

n_pri=$(q "SELECT count(*) FROM user_ai_reports WHERE user_key='$USER_KEY' AND report_role='primary';")
n_sha=$(q "SELECT count(*) FROM user_ai_reports WHERE user_key='$USER_KEY' AND report_role='shadow';")

[ "$n_pri" -gt 0 ] && ok "primary (learner-facing) report exists ($n_pri)" \
                   || bad "no primary report" "user in control group, or AI generation failed"

pri_model=$(q "SELECT model FROM user_ai_reports WHERE user_key='$USER_KEY' AND report_role='primary' ORDER BY id DESC LIMIT 1;")
if [ "$n_sha" -gt 0 ]; then
  ok "shadow (rule-based) report exists ($n_sha) — pair available for expert rating"
elif [[ "$pri_model" == *rule* ]]; then
  warn "no shadow report, but primary is '$pri_model'" "correct behaviour: pairing rule-based with rule-based is meaningless. Re-run the pilot with working API keys to exercise the real path."
else
  bad "primary is LLM ('$pri_model') but no shadow was written" "RQ4 will have no comparison data"
fi

# the safety property
served=$(q "SELECT model FROM user_ai_reports WHERE user_key='$USER_KEY' AND report_role='primary' ORDER BY generated_at DESC, id DESC LIMIT 1;")
unfiltered=$(q "SELECT model FROM user_ai_reports WHERE user_key='$USER_KEY' ORDER BY generated_at DESC, id DESC LIMIT 1;")
if [ "$served" = "$unfiltered" ]; then
  ok "learner-facing query returns '$served'"
else
  ok "role filter is doing real work (filtered='$served' vs unfiltered='$unfiltered')"
fi
[[ "$served" == *shadow* ]] && bad "learner would be served a SHADOW report" "role filter broken — do not enrol participants"

# ---------------------------------------------------------------- expert rating path
hdr "6. Expert rating path (rolled back)"

ins=$(q "BEGIN;
INSERT INTO feedback_rating (rater_id,participant_code,round_no,feedback_source,relevance,specificity,actionability,accuracy,model_name,comment)
VALUES ('PILOT','PILOT',1,'gemini',4,4,4,4,'pilot-check','rolled back')
ON CONFLICT (rater_id,participant_code,round_no,feedback_source) DO NOTHING;
ROLLBACK;")
[[ "$ins" == *ERROR* ]] && bad "store_feedback_rating() path fails" "$ins" \
                        || ok "feedback_rating insert path works (rolled back)"

er=$(q "BEGIN;
INSERT INTO expert_rating (rater_id,participant_code,round_no,dimension,score)
VALUES ('PILOT','PILOT',1,'accuracy_score',80)
ON CONFLICT (rater_id,participant_code,round_no,dimension) DO NOTHING;
ROLLBACK;")
[[ "$er" == *ERROR* ]] && bad "expert_rating insert path fails" "$er" \
                       || ok "expert_rating insert path works (rolled back)"

# ---------------------------------------------------------------- analysis path
hdr "7. Analysis path"

h1=$(q "SELECT count(*) FROM user_skill_reports r LEFT JOIN experiment_assignment e ON r.user_key=CAST(e.user_id AS TEXT) WHERE r.round_no=1;")
[[ "$h1" == *ERROR* ]] && bad "H1 analysis query fails" "$h1" \
                      || ok "H1 analysis query runs (round 1 rows: $h1)"

if [ -d "$REPO" ]; then
  n_asg=$(q "SELECT count(*) FROM experiment_assignment;")
  [ "$n_asg" -gt 0 ] && ok "experiment_assignment populated ($n_asg)" \
                     || warn "experiment_assignment is empty" "pilot users were not enrolled via assign_participant()"
else
  warn "repo not found at $REPO" "skipped provenance/analysis script checks"
fi

# ---------------------------------------------------------------- cleanliness
hdr "8. Research-data cleanliness"

sim=$(q "SELECT count(*) FROM events WHERE user_key LIKE 'bank.s%' OR user_key LIKE 'mint.s%' OR user_key LIKE 'oak.s%';")
[ "$sim" = "0" ] && ok "no simulation users in events" || bad "$sim simulation events present" "must be wiped before real collection"

trg=$(q "SELECT count(*) FROM pg_trigger WHERE tgrelid='events'::regclass AND NOT tgisinternal;")
[ "$trg" -ge 1 ] && ok "append-only trigger on events is present" \
                 || bad "no trigger on events" "research integrity guarantee missing"

# ---------------------------------------------------------------- summary
echo
echo "==============================================================="
printf ' PASS %d   FAIL %d   WARN %d\n' "$PASS" "$FAIL" "$WARN"
echo "==============================================================="
cat <<'MANUAL'

STILL REQUIRES A HUMAN (cannot be automated):
  [ ] Open /report as the pilot participant and confirm the text shown is the
      LLM report, not the rule-based one. Compare against the DB row.
  [ ] Read one generated report end to end: is it in Thai, does it cite concrete
      evidence values, and is it free of claims the data does not support?
  [ ] Submit the post-round survey as a participant and confirm it stores.
  [ ] Confirm a CONTROL-group user sees NO feedback report.
  [ ] Temporarily unset the API keys, regenerate, and confirm a rule-based report
      still appears (fallback works, no blank page).

BEFORE ENROLLING REAL PARTICIPANTS:
  [ ] bash tools/setup/reset_for_data_collection.sh     (wipes pilot data)
  [ ] python tools/research/verify_data_provenance.py   (expect 0 users)
  [ ] Confirm pre-registration is filed and locked.
MANUAL

[ "$FAIL" -eq 0 ] || exit 1
