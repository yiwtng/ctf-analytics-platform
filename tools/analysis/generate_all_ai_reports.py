#!/usr/bin/env python3
"""
Generate skill + AI reports for every user_key that has analytics events.

Calls orchestrator POST /generate_report/{user_key} with a gap between users
to reduce Gemini rate limits (see GENERATE_REPORT_ALL_GAP_SECONDS in orchestrator).

Usage:
    python3 ctfd_tools/generate_all_ai_reports.py
    ORCH_BASE=http://orch.example.com python3 ctfd_tools/generate_all_ai_reports.py

Environment:
    ORCH_BASE   (default: from env or http://orch.100.113.75.64.nip.io)
    REPORT_GAP  seconds between users (default: 15)
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

ORCH_BASE = os.getenv("ORCH_BASE", "http://orch.100.113.75.64.nip.io").rstrip("/")
REPORT_GAP = float(os.getenv("REPORT_GAP", "15"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))


def main() -> None:
    r = requests.get(f"{ORCH_BASE}/report_all", timeout=60)
    r.raise_for_status()
    data = r.json()
    reports = data.get("reports") or []
    users = [item.get("user_key") for item in reports if item.get("user_key")]
    users = sorted(set(users))

    print(f"ORCH_BASE={ORCH_BASE}", flush=True)
    print(f"Users with events: {len(users)}", flush=True)

    ok = 0
    errors: list[dict] = []

    for i, user_key in enumerate(users):
        try:
            resp = requests.post(
                f"{ORCH_BASE}/generate_report/{user_key}",
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                ok += 1
                body = resp.json()
                print(
                    f"[{i+1}/{len(users)}] OK {user_key} "
                    f"ai_report_id={body.get('ai_report_id')}",
                    flush=True,
                )
            else:
                errors.append({"user_key": user_key, "http": resp.status_code, "text": resp.text[:500]})
                print(f"[{i+1}/{len(users)}] FAIL {user_key} HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            errors.append({"user_key": user_key, "error": str(exc)})
            print(f"[{i+1}/{len(users)}] FAIL {user_key} {exc}", flush=True)

        if i < len(users) - 1 and REPORT_GAP > 0:
            time.sleep(REPORT_GAP)

    summary = {"total": len(users), "ok": ok, "errors": len(errors), "error_detail": errors}
    out_path = os.getenv("GENERATE_ALL_SUMMARY_JSON", "/tmp/generate_all_ai_reports_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"Wrote {out_path}", flush=True)
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
