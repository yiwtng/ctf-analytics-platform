import csv
import os
import random
import time
from typing import Dict, List

import requests

ORCH_URL = os.getenv("ORCH_URL", "http://orch.10.211.55.3.nip.io")
USERS_CSV = os.getenv("USERS_CSV", "./ctfd_tools/users.csv")


POSITIVE_OPENERS = [
    "โดยรวมแล้วระบบใช้งานได้ดี",
    "ภาพรวมของการแข่งขันถือว่าดีมาก",
    "ประสบการณ์ใช้งานโดยรวมค่อนข้างดี",
    "ระบบมีความน่าสนใจและใช้งานได้ต่อเนื่อง",
    "การแข่งขันครั้งนี้ให้ประสบการณ์ที่ดี",
]

LIKED_PARTS = [
    "ชอบที่โจทย์มีหลายรูปแบบ ทั้ง web, protocol และ ssh ทำให้ได้ลองคิดหลายมุม",
    "ชอบบรรยากาศของระบบและธีมหน้าเว็บ ดูเหมือนสนามฝึกจริง",
    "ชอบที่สามารถกด start instance แล้วทดลองกับ service ได้ทันที",
    "ชอบรายงานหลังจบเกม เพราะช่วยให้เห็นจุดแข็งและจุดที่ควรพัฒนา",
    "ชอบที่โจทย์มีความต่อเนื่องและทำให้รู้สึกเหมือนกำลังแก้ปัญหาในสถานการณ์จริง",
    "ชอบความชัดเจนของหน้า challenge และการแสดงผลคำสั่งเชื่อมต่อ",
    "ชอบที่ระบบพยายามสรุปพฤติกรรมการเล่น ไม่ได้ดูแค่คะแนนอย่างเดียว",
]

IMPROVEMENT_POINTS = [
    "บางช่วงการเริ่ม instance ใช้เวลานานเล็กน้อย ถ้าลดเวลาได้จะดีขึ้นมาก",
    "อยากให้คำใบ้บางข้อชัดเจนขึ้นอีกเล็กน้อยสำหรับผู้เล่นที่พื้นฐานยังไม่มาก",
    "บางโจทย์ควรมีคำอธิบายบริบทเพิ่มอีกนิด เพื่อให้เข้าใจเป้าหมายเร็วขึ้น",
    "อยากให้หน้า feedback และ report เชื่อมกันลื่นขึ้น เช่น submit เสร็จแล้วไปหน้ารายงานทันที",
    "ถ้ามีตัวอย่างรูปแบบคำตอบหรือแนวทางเริ่มต้นในบางโจทย์จะช่วยผู้เล่นใหม่ได้มากขึ้น",
    "อยากให้มีการแจ้งสถานะว่า instance พร้อมใช้งานแล้วแบบชัดเจนขึ้น",
    "บางข้อความในระบบยังเป็นเชิงเทคนิคพอสมควร ถ้าปรับให้อ่านง่ายขึ้นจะดีมาก",
]

EXTRA_COMMENTS = [
    "เหมาะกับการใช้ฝึกก่อนลงแข่งจริง และสามารถต่อยอดในงานวิจัยได้ดี",
    "รู้สึกว่าระบบนี้มีศักยภาพในการใช้เป็นสนามฝึกสำหรับนักศึกษาหรือผู้เริ่มต้นสายไซเบอร์",
    "ถ้ามี dashboard สำหรับผู้สอนหรือผู้ดูแลเพื่อดูพฤติกรรมรวมจะมีประโยชน์มาก",
    "ส่วนของคำแนะนำเฉพาะบุคคลเป็นจุดที่น่าสนใจและแตกต่างจาก CTF ทั่วไป",
    "โดยรวมถือว่าเป็นระบบที่มีแนวคิดดีและสามารถพัฒนาต่อเป็น production ได้",
    "หลังทำแบบประเมินแล้วอยากเห็นสรุปผลของตัวเองต่อทันที จะช่วยให้ประสบการณ์ครบมากขึ้น",
    "",
    "",
]

LEARNING_COMMENTS = [
    "ได้ฝึกการคิดเป็นขั้นตอนมากขึ้น โดยเฉพาะการสังเกตพฤติกรรมของ service ก่อนลงมือจริง",
    "ได้เรียนรู้ว่าการแก้โจทย์ไม่ได้ดูแค่คำตอบสุดท้าย แต่กระบวนการทดลองก็สำคัญ",
    "ได้ฝึกวิเคราะห์ระบบจากข้อมูลเล็ก ๆ เช่น banner, response และ hint",
    "ได้ทบทวนพื้นฐานเรื่อง protocol, web interaction และการสำรวจระบบผ่าน command line",
    "ทำให้เห็นว่าการเก็บ log พฤติกรรมผู้เล่นสามารถนำไปต่อยอดเป็นคำแนะนำรายบุคคลได้",
]

STYLE_PROFILES = [
    {
        "name": "positive",
        "usability": [4, 5],
        "challenge_quality": [4, 5],
        "recommendation_quality": [4, 5],
        "confidence": [4, 5],
    },
    {
        "name": "balanced",
        "usability": [3, 4, 5],
        "challenge_quality": [3, 4, 5],
        "recommendation_quality": [3, 4, 5],
        "confidence": [3, 4, 5],
    },
    {
        "name": "critical_but_fair",
        "usability": [3, 4],
        "challenge_quality": [3, 4, 5],
        "recommendation_quality": [3, 4],
        "confidence": [3, 4],
    },
]


def load_users(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def choose_profile(username: str) -> Dict[str, List[int]]:
    idx = sum(ord(c) for c in username) % len(STYLE_PROFILES)
    return STYLE_PROFILES[idx]


def build_favorite_part() -> str:
    parts = random.sample(LIKED_PARTS, k=random.choice([1, 1, 2]))
    learning = random.choice(LEARNING_COMMENTS)
    text = " ".join(parts)
    if random.random() < 0.7:
        text += " " + learning
    return text.strip()


def build_improvement_point() -> str:
    parts = random.sample(IMPROVEMENT_POINTS, k=random.choice([1, 1, 2]))
    return " ".join(parts).strip()


def build_comments() -> str:
    opener = random.choice(POSITIVE_OPENERS)
    extra = random.choice(EXTRA_COMMENTS)
    if extra:
        return f"{opener} {extra}".strip()
    return opener.strip()


def build_payload(username: str) -> Dict:
    profile = choose_profile(username)
    return {
        "user_key": username,
        "usability_score": random.choice(profile["usability"]),
        "challenge_quality_score": random.choice(profile["challenge_quality"]),
        "recommendation_quality_score": random.choice(profile["recommendation_quality"]),
        "confidence_improvement_score": random.choice(profile["confidence"]),
        "favorite_part": build_favorite_part(),
        "improvement_point": build_improvement_point(),
        "comments": build_comments(),
    }


def submit_feedback(payload: Dict) -> requests.Response:
    return requests.post(
        f"{ORCH_URL}/participant_feedback",
        json=payload,
        timeout=10,
    )


def main():
    users = load_users(USERS_CSV)

    print(f"[*] Loaded {len(users)} users from {USERS_CSV}")
    print(f"[*] Submitting feedback to {ORCH_URL}/participant_feedback")

    for row in users:
        username = row["username"].strip()
        payload = build_payload(username)

        try:
            resp = submit_feedback(payload)
            if resp.ok:
                print(f"[+] submitted feedback for {username}")
            else:
                print(f"[!] failed for {username}: status={resp.status_code} body={resp.text[:300]}")
        except Exception as e:
            print(f"[!] error for {username}: {e}")

        time.sleep(random.uniform(0.4, 1.2))


if __name__ == "__main__":
    main()
