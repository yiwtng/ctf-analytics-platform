import csv
import os
import sys
import requests

CTFD_URL = os.getenv("CTFD_URL", "http://ctf.10.211.55.3.nip.io")
CTFD_TOKEN = os.getenv("CTFD_TOKEN", "")
CSV_PATH = os.getenv("USERS_CSV", "./ctfd_tools/users.csv")

if not CTFD_TOKEN:
    print("Missing CTFD_TOKEN")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Token {CTFD_TOKEN}",
    "Content-Type": "application/json",
}

def create_user(row: dict) -> None:
    payload = {
        "name": row["username"],
        "email": row["email"],
        "password": row["password"],
        "type": "user",
        "verified": True,
        "hidden": False,
        "banned": False,
    }

    r = requests.post(
        f"{CTFD_URL}/api/v1/users",
        headers=HEADERS,
        json=payload,
        timeout=20,
    )

    if r.ok:
        print(f"[+] created {row['username']}")
        return

    try:
        data = r.json()
    except Exception:
        data = {"error": r.text}

    # ถ้าซ้ำ ให้ถือว่าผ่าน
    if r.status_code in (400, 409):
        print(f"[=] skipped {row['username']} -> {data}")
        return

    print(f"[!] failed {row['username']} -> {r.status_code} {data}")

def main() -> None:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            create_user(row)

if __name__ == "__main__":
    main()
