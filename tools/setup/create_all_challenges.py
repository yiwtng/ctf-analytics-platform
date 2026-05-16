import os
import sys
from typing import Any, Dict, List, Optional

import requests

CTFD_URL = os.getenv("CTFD_URL", "http://ctf.10.211.55.3.nip.io").rstrip("/")
CTFD_TOKEN = os.getenv("CTFD_TOKEN", "").strip()

HEADERS = {
    "Authorization": f"Token {CTFD_TOKEN}",
    "Content-Type": "application/json",
}

TIMEOUT = 30


RED_CHALLENGES: List[Dict[str, Any]] = [
    {
        "name": "Red - Ghost Login",
        "category": "Red Team",
        "value": 100,
        "instance_challenge_id": "red_ghost_login",
        "flag": "flag{d45179d1b1562e1f334dcba5e88e9199}",
        "overview": "Investigate the login workflow and identify hidden functionality.",
        "access": "Click Start Instance to receive your target URL.",
        "hint_text": "Try inspecting hidden endpoints or debug paths.",
        "type_label": "Web Interactive",
        "hints": [
            {"content": "Do not trust the obvious login form too quickly.", "cost": 10},
        ],
    },
    {
        "name": "Red - Protocol Probe",
        "category": "Red Team",
        "value": 150,
        "instance_challenge_id": "red_protocol_probe",
        "flag": "flag{a70526764755d9fd890c030d71a1c559}",
        "overview": "Interact with the TCP service and understand the protocol flow.",
        "access": "Click Start Instance to receive the nc command.",
        "hint_text": "Observe the banner and server responses carefully.",
        "type_label": "NC / TCP Interactive",
        "hints": [
            {"content": "The banner tells you how to begin.", "cost": 10},
        ],
    },
    {
        "name": "Red - Pivot Notes",
        "category": "Red Team",
        "value": 200,
        "instance_challenge_id": "red_pivot_notes",
        "flag": "flag{3a94ecb064f591a63c5a0644e4844f26}",
        "overview": "Access the SSH environment and inspect the host to recover the target flag.",
        "access": "Click Start Instance to receive SSH connection details.",
        "hint_text": "A basic inspection of the home directory may help.",
        "type_label": "SSH Interactive",
        "hints": [
            {"content": "A basic inspection of the home directory may help.", "cost": 10},
        ],
    },
    {
        "name": "Red - Log Poisoning",
        "category": "Red Team",
        "value": 180,
        "instance_challenge_id": "red_log_poisoning",
        "flag": "flag{344d59b6084a1d4d1ecb89a692fcf13c}",
        "overview": "Inject payloads into the logging workflow and recover the hidden flag from the log interface.",
        "access": "Click Start Instance to receive your target URL.",
        "hint_text": "Interact with the app, then inspect log-related behavior.",
        "type_label": "Web Interactive",
        "hints": [
            {"content": "User-controlled input is written somewhere persistent.", "cost": 10},
            {"content": "A log-related endpoint may expose what has been recorded.", "cost": 15},
        ],
    },
]

BLUE_CHALLENGES: List[Dict[str, Any]] = [
    {
        "name": "Blue - Misleading Intel",
        "category": "Blue Team",
        "value": 100,
        "difficulty": "Easy",
        "flag": "flag{185.199.108.153}",
        "overview": "Analyze the incident notes and identify the real malicious IP address.",
        "flag_format": "flag{ip_address}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Incident Notes: Suspicious Outbound Traffic
-------------------------------------------
Case ID: SOC-2026-041
Host Group: Finance Workstations
Analyst: Tier-1 Night Shift

Summary:
At approximately 08:41, the SOC observed repeated outbound connections associated with a workstation later identified
as WS-FIN-07. The first review of temporary analyst notes listed several addresses that appeared during the response.

Collected IP references:
- 10.10.4.8
- 185.199.108.153
- 172.16.1.25
- 192.168.56.24

Additional context:
- 10.10.4.8 was confirmed as an internal application server.
- 172.16.1.25 belongs to a lab VLAN used for malware detonation.
- 192.168.56.24 appears in old VPN documentation but is not active in this incident.
- The external destination was contacted repeatedly after a local archive file was created.

Firewall Snippet:
08:48:11 ALLOW WS-FIN-07 -> 185.199.108.153:443
08:48:14 ALLOW WS-FIN-07 -> 185.199.108.153:443
08:48:19 ALLOW WS-FIN-07 -> 185.199.108.153:443

Question:
Which IP is the real malicious destination in this incident?
</pre>
""".strip(),
        "hints": [
            {"content": "Separate private/internal addresses from external/public addresses first.", "cost": 10},
        ],
    },
    {
        "name": "Blue - Slow Think Fast Guess",
        "category": "Blue Team",
        "value": 100,
        "difficulty": "Easy",
        "flag": "flag{powershell}",
        "overview": "Read the alert summary carefully and identify the execution tool used by the attacker.",
        "flag_format": "flag{tool_name}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Alert Summary: Suspicious Script Execution
------------------------------------------
Hostname: WS-FIN-07
User: finance.ops
Date: 2026-03-31

Observed behavior:
- Encoded command execution observed from endpoint telemetry
- Child process spawned from explorer.exe
- Network beaconing started within 30 seconds of script execution
- Temporary ZIP archive created in user temp path
- Analyst note: likely living-off-the-land execution technique

Process Notes:
Parent: explorer.exe
Child: unknown shell execution
Commandline indicator:
  -EncodedCommand SQBtAHAAbwByAHQAYQBuAHQAIABhAGwAZQByAHQ...

Response Team Comment:
This tool is often used when attackers want to execute obfuscated administrative scripts.

Question:
Which tool or shell was most likely used by the attacker?
</pre>
""".strip(),
        "hints": [
            {"content": "Focus on the phrase 'EncodedCommand'.", "cost": 10},
        ],
    },
    {
        "name": "Blue - Hint Dependency",
        "category": "Blue Team",
        "value": 150,
        "difficulty": "Medium",
        "flag": "flag{svc-backup}",
        "overview": "Determine the first suspicious account from the activity timeline.",
        "flag_format": "flag{account_name}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Timeline Extract: Unauthorized Activity Review
----------------------------------------------
08:41 - Successful login by j.smith from 10.20.1.14
08:43 - User opened finance dashboard
08:45 - Scheduled task modified on WS-FIN-07
08:47 - Successful login by svc-backup from 192.168.56.24
08:48 - Archive file created in C:\Users\finance.ops\AppData\Local\Temp
08:49 - Registry persistence key updated
08:52 - Outbound connection established to 185.199.108.153
08:57 - Incident escalated to Tier-2
09:01 - Temporary account review initiated

Analyst Notes:
- j.smith is a normal interactive employee account.
- svc-backup is documented as a service account and normally should not perform interactive login.
- The suspicious login occurred shortly before archive creation and outbound transfer.

Question:
Which account appears to be the first suspicious account in this timeline?
</pre>
""".strip(),
        "hints": [
            {"content": "Look for an account behaving outside its normal role.", "cost": 10},
            {"content": "The suspicious account appears before the outbound transfer.", "cost": 15},
        ],
    },
    {
        "name": "Blue - Multi-stage Flag",
        "category": "Blue Team",
        "value": 200,
        "difficulty": "Medium",
        "flag": "flag{ws-fin-07_powershell_185.199.108.153}",
        "overview": "Recover hostname, tool, and exfil destination from the report, then combine them into one flag.",
        "flag_format": "flag{hostname_tool_ip}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Incident Report: Consolidated Findings
--------------------------------------
Host involved:
- WS-FIN-07

Execution findings:
- Encoded command execution was detected
- Parent-child chain strongly suggested PowerShell abuse
- Script activity preceded creation of a temporary ZIP file

Network findings:
- Repeated outbound connections to 185.199.108.153
- Activity occurred shortly after local archive creation
- Traffic pattern was consistent with staged exfiltration

Flag construction rule:
flag{hostname_tool_ip}

Formatting notes:
- Use lowercase
- Replace spaces with underscores if needed
- Use exact values from the report

Example:
flag{ws-fin-07_powershell_1.2.3.4}

Question:
Construct the final flag.
</pre>
""".strip(),
        "hints": [
            {"content": "All three required parts are explicitly present in the report.", "cost": 10},
            {"content": "Use lowercase exactly as shown in the example format.", "cost": 15},
        ],
    },
    {
        "name": "Blue - Beacon Pattern",
        "category": "Blue Team",
        "value": 120,
        "difficulty": "Easy",
        "flag": "flag{60}",
        "overview": "Identify the beacon interval in seconds from the network telemetry.",
        "flag_format": "flag{seconds}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Network Telemetry: Repeating Outbound Requests
----------------------------------------------
Host: WS-MKT-02
Destination: 198.51.100.77
Port: 443

Observed connection timestamps:
10:00:05
10:01:05
10:02:05
10:03:05
10:04:05
10:05:05

Analyst Notes:
- Traffic is highly regular and low volume
- Pattern resembles beaconing rather than user-driven browsing
- No corresponding browser activity was recorded at these times

Question:
What is the beacon interval in seconds?
</pre>
""".strip(),
        "hints": [
            {"content": "Check the difference between consecutive timestamps.", "cost": 10},
        ],
    },
    {
        "name": "Blue - Suspicious Archive",
        "category": "Blue Team",
        "value": 160,
        "difficulty": "Medium",
        "flag": "flag{finance_q1_2026.zip}",
        "overview": "Identify the archive file that was most likely prepared for exfiltration.",
        "flag_format": "flag{filename}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
File Activity Review
--------------------
Host: WS-FIN-07
User: finance.ops

Recent file events:
08:32 - Opened budget_draft.xlsx
08:37 - Opened payroll_notes.docx
08:46 - Created finance_q1_2026.zip in Temp
08:47 - Modified personal_photo.jpg
08:48 - Outbound connection to 185.199.108.153
08:49 - Deleted temp text file notes.tmp
08:55 - ZIP handle no longer active

Analyst Comments:
- Archive creation immediately preceded outbound transfer
- Filename appears business-related
- Temporary location suggests staging rather than long-term storage

Question:
Which file was most likely staged for exfiltration?
</pre>
""".strip(),
        "hints": [
            {"content": "Look for the file created just before outbound traffic.", "cost": 10},
        ],
    },
    {
        "name": "Blue - Lateral Movement Clue",
        "category": "Blue Team",
        "value": 180,
        "difficulty": "Hard",
        "flag": "flag{10.20.5.19}",
        "overview": "Identify the internal destination that suggests lateral movement.",
        "flag_format": "flag{ip_address}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Authentication and Connection Review
------------------------------------
Compromised Host: WS-HR-03

Relevant events:
11:14 - login success by hr.assistant from 10.20.3.44
11:18 - remote service creation event detected
11:19 - SMB connection from WS-HR-03 to 10.20.5.19
11:20 - ADMIN$ share access recorded
11:22 - failed login to 10.20.8.7
11:24 - successful authentication using reused credentials
11:26 - suspicious service start on remote host
11:29 - new scheduled task observed

Analyst Notes:
- External traffic is not the focus of this case
- We are interested in identifying the most likely internal host targeted during lateral movement
- ADMIN$ access combined with remote service activity is a strong clue

Question:
Which internal IP most strongly indicates lateral movement?
</pre>
""".strip(),
        "hints": [
            {"content": "Look for the host associated with ADMIN$ and remote service activity.", "cost": 10},
            {"content": "The first strong lateral movement clue appears before the failed login to 10.20.8.7.", "cost": 15},
        ],
    },
    {
        "name": "Blue - Persistence Finder",
        "category": "Blue Team",
        "value": 200,
        "difficulty": "Hard",
        "flag": "flag{run_registry_key}",
        "overview": "Determine the persistence mechanism used by the attacker.",
        "flag_format": "flag{mechanism}",
        "artifact": r"""
<pre style="white-space:pre-wrap;line-height:1.7;">
Endpoint Persistence Findings
-----------------------------
Host: WS-FIN-07

Collected indicators:
- New value written under HKCU\Software\Microsoft\Windows\CurrentVersion\Run
- Script placed in user profile startup location was NOT observed
- Scheduled task was modified earlier, but later analysis showed no malicious payload remained there
- WMI subscription artifacts were checked and found clean
- The registry write occurred shortly after suspicious login and before outbound communication

Analyst Reasoning:
The attacker likely selected a persistence method that would execute when the user logs in again.

Question:
What persistence mechanism was used?

Expected answer style:
run_registry_key
</pre>
""".strip(),
        "hints": [
            {"content": "Focus on the confirmed artifact, not the earlier misleading scheduled task clue.", "cost": 10},
            {"content": "The mechanism is related to the Windows Run registry location.", "cost": 15},
        ],
    },
]


def require_token() -> None:
    if not CTFD_TOKEN:
        raise SystemExit("Missing CTFD_TOKEN")


def api_request(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{CTFD_URL}{path}"
    resp = requests.request(method, url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def list_challenges() -> List[Dict[str, Any]]:
    resp = api_request("GET", "/api/v1/challenges")
    data = resp.json().get("data", [])
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return data


def find_challenge_by_name(name: str) -> Optional[Dict[str, Any]]:
    for chal in list_challenges():
        if chal.get("name") == name:
            return chal
    return None


def delete_challenge(challenge_id: int) -> None:
    api_request("DELETE", f"/api/v1/challenges/{challenge_id}")


def build_red_description(chal: Dict[str, Any]) -> str:
    instance_challenge_id = chal["instance_challenge_id"]
    return f"""
<p><strong>Overview:</strong> {chal["overview"]}</p>
<p><strong>Access:</strong> {chal["access"]}</p>
<p><strong>Hint:</strong> {chal["hint_text"]}</p>
<p><strong>Type:</strong> {chal["type_label"]}</p>
<p><strong>Instance Challenge ID:</strong> <code>{instance_challenge_id}</code></p>

<div style="margin:14px 0 18px 0;">
  <button class="start-instance-btn"
    data-challenge-id="{instance_challenge_id}"
    style="
      width:100%;
      max-width:220px;
      display:block;
      background:#2f6fed;
      color:white;
      padding:12px 16px;
      border:none;
      border-radius:10px;
      font-weight:600;
      cursor:pointer;
      box-shadow:0 0 10px rgba(47,111,237,0.25);
    ">
    ▶ Start Instance
  </button>

  <div class="instance-output"
    style="
      margin-top:12px;
      padding:12px 14px;
      border-radius:10px;
      background:#0c1322;
      border:1px solid #1b2940;
      display:none;
      color:#e6f0ff;
      line-height:1.6;
      word-break:break-word;
    ">
  </div>
</div>

<div style="height:6px;"></div>

<p style="margin-top:8px;color:#9fb3d1;">
  <strong>Research Note:</strong> Interactions in this challenge may be recorded for behavioral analysis.
</p>
""".strip()


def build_blue_description(chal: Dict[str, Any]) -> str:
    return f"""
<p><strong>Overview:</strong> {chal["overview"]}</p>
<p><strong>Difficulty:</strong> {chal["difficulty"]}</p>
<p><strong>Flag format:</strong> <code>{chal["flag_format"]}</code></p>

<div style="
  margin:14px 0 18px 0;
  padding:12px 14px;
  border-radius:10px;
  background:#0c1322;
  border:1px solid #1b2940;
  color:#e6f0ff;
  line-height:1.6;
  word-break:break-word;
">
  {chal["artifact"]}
</div>

<p style="margin-top:8px;color:#9fb3d1;">
  <strong>Research Note:</strong> Submission behavior in this challenge may be recorded for behavioral analysis.
</p>
""".strip()


def create_challenge(chal: Dict[str, Any], description: str) -> int:
    payload = {
        "name": chal["name"],
        "category": chal["category"],
        "description": description,
        "value": chal["value"],
        "type": "standard",
        "state": "visible",
    }
    resp = api_request("POST", "/api/v1/challenges", json=payload)
    return resp.json()["data"]["id"]


def create_flag(challenge_id: int, content: str) -> None:
    payload = {
        "challenge_id": challenge_id,
        "type": "static",
        "content": content,
        "data": "",
    }
    api_request("POST", "/api/v1/flags", json=payload)


def create_hint(challenge_id: int, content: str, cost: int) -> None:
    payload = {
        "challenge_id": challenge_id,
        "content": content,
        "cost": cost,
        "requirements": None,
    }
    api_request("POST", "/api/v1/hints", json=payload)


def recreate_challenge(chal: Dict[str, Any], description: str) -> None:
    existing = find_challenge_by_name(chal["name"])
    if existing:
        challenge_id = existing["id"]
        print(f"[-] Deleting existing challenge: {chal['name']} (id={challenge_id})")
        delete_challenge(challenge_id)

    challenge_id = create_challenge(chal, description)
    create_flag(challenge_id, chal["flag"])

    for hint in chal.get("hints", []):
        create_hint(challenge_id, hint["content"], hint["cost"])

    print(f"[+] Created: {chal['name']} (id={challenge_id})")


def create_red_challenges() -> bool:
    print(f"[*] Recreating {len(RED_CHALLENGES)} red challenges...")
    failed = False
    for chal in RED_CHALLENGES:
        try:
            recreate_challenge(chal, build_red_description(chal))
        except Exception as exc:
            failed = True
            print(f"[!] Failed: {chal['name']} -> {exc}")
    return failed


def create_blue_challenges() -> bool:
    print(f"[*] Recreating {len(BLUE_CHALLENGES)} blue challenges...")
    failed = False
    for chal in BLUE_CHALLENGES:
        try:
            recreate_challenge(chal, build_blue_description(chal))
        except Exception as exc:
            failed = True
            print(f"[!] Failed: {chal['name']} -> {exc}")
    return failed


def main() -> None:
    require_token()

    mode = os.getenv("CHALLENGE_SET", "all").strip().lower()
    print(f"[*] CTFD_URL = {CTFD_URL}")
    print(f"[*] Mode = {mode}")

    failed = False

    if mode in {"all", "red"}:
        failed = create_red_challenges() or failed

    if mode in {"all", "blue"}:
        failed = create_blue_challenges() or failed

    if mode not in {"all", "red", "blue"}:
        raise SystemExit("CHALLENGE_SET must be one of: all, red, blue")

    if failed:
        sys.exit(1)

    print("[+] Done")


if __name__ == "__main__":
    main()
