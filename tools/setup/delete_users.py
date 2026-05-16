import os
import requests
import csv

CTFD_URL = os.getenv("CTFD_URL", "http://ctf.10.211.55.3.nip.io")
CTFD_TOKEN = os.getenv("CTFD_TOKEN", "")

USERS_CSV = os.getenv("USERS_CSV", "./ctfd_tools/users.csv")

HEADERS = {
    "Authorization": f"Token {CTFD_TOKEN}",
    "Content-Type": "application/json",
}


def get_all_users():
    r = requests.get(f"{CTFD_URL}/api/v1/users", headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()["data"]


def delete_user(user_id):
    r = requests.delete(f"{CTFD_URL}/api/v1/users/{user_id}", headers=HEADERS, timeout=20)
    r.raise_for_status()


def load_target_usernames():
    with open(USERS_CSV, newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        return [r["username"] for r in rows]


def main():
    if not CTFD_TOKEN:
        raise SystemExit("❌ Missing CTFD_TOKEN")

    targets = set(load_target_usernames())
    users = get_all_users()

    print(f"[*] Found {len(users)} users in CTFd")
    print(f"[*] Will delete {len(targets)} users from CSV")

    for u in users:
        username = u.get("name")
        user_id = u.get("id")

        if username in targets:
            try:
                delete_user(user_id)
                print(f"[+] Deleted: {username} (id={user_id})")
            except Exception as e:
                print(f"[!] Failed: {username} -> {e}")

    print("[✓] Done")


if __name__ == "__main__":
    main()
