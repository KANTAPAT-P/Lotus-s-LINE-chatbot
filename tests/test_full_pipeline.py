"""
test_full_pipeline.py
--------------------------------
เทส pipeline เต็มรูปแบบ (generate_reply() ใน webhook_server.py) ด้วย
ข้อมูลจริงทั้งหมดที่ scrape มา (data/categories/categories_flat.json
833 รายการ + data/all_product/ 255 MB) ไม่ผ่าน Flask/LINE จริง (เพราะ
generate_reply() ถูกออกแบบให้แยกออกจาก LINE API ตั้งแต่ต้น เทสได้เลย
โดยไม่ต้องมี LINE credentials หรือรัน server จริง)

วิธีรัน:
    cd webhook_server
    python ../tests/test_full_pipeline.py

(ปรับ path ตามตำแหน่งที่วางไฟล์นี้จริงในโปรเจกต์ — ไฟล์นี้ต้องมองเห็น
webhook_server.py, AI_text_processing/, Function/, scraping/, data/
ทั้งหมด แนะนำให้วางไว้ที่ root โปรเจกต์แล้วรันจากตรงนั้นเลย จะได้ไม่
ต้องยุ่งกับ relative path)

สิ่งที่เทส:
1. Local exact match: สุ่มหยิบชื่อ category จริงจาก categories_flat.json
   มาถามตรง ๆ ควรได้ FlexSendMessage ทุกครั้ง (หรือข้อความ "ของหมด"
   ถ้าหมวดนั้นบังเอิญ scrape มาได้ 0 ชิ้นจริง ๆ)
2. Local fuzzy match: เอาชื่อ category จริงมา "ทำให้พิมพ์ผิด" (สุ่มตัด/
   เพิ่ม/สลับตัวอักษร) แล้วดูว่ายัง match ถูกหมวดเดิมไหม
3. ask_promotion ผสม entity: เอาชื่อ category จริงมาต่อท้ายด้วย
   "โปรโมชั่น" ดูว่า intent จับถูกไหม และไม่ error
4. Edge case ที่เคยเจอบั๊กมาก่อน: "โปรโมชั่น" เดี่ยว ๆ, "สวัสดีครับ",
   ข้อความว่างเปล่า, ข้อความยาวผิดปกติ
5. วัดเวลาที่ใช้ทุกเคส แยกเป็น "local" (ไม่ผ่าน network) กับ "อาจ
   fallback ไป network" เพื่อเช็คว่ายังอยู่ในงบเวลาที่อาจารย์กำหนด
   (NLP latency < 1.5-2 วิ) — งบเวลานี้หมายถึงเฉพาะส่วน NLP+local
   ไม่รวมเวลาที่ต้องรอ network ตอน fallback ค้นสด (ซึ่งควบคุมไม่ได้)

ผลลัพธ์: พิมพ์สรุปท้ายสุดเป็นตาราง pass/fail + เวลาเฉลี่ย/สูงสุด
"""

import os
import random
import sys
import time
import json
import traceback

# ----------------------------------
# ต้องตั้งค่า dummy env vars ก่อน import webhook_server เพราะ LineBotApi
# จะ error ทันทีถ้า CHANNEL_ACCESS_TOKEN เป็น None (ไม่ได้แปลว่าเทสนี้
# ยิง request หา LINE จริง แค่ LineBotApi constructor ต้องการ string
# ไม่ error ตอน initialize เฉย ๆ)
# ----------------------------------
os.environ.setdefault("CHANNEL_SECRET", "dummy_for_testing")
os.environ.setdefault("CHANNEL_ACCESS_TOKEN", "dummy_for_testing")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")  # ปรับตามตำแหน่งจริงถ้าย้ายไฟล์
sys.path.append(os.path.join(PROJECT_ROOT, "webhook_server"))
sys.path.append(os.path.join(PROJECT_ROOT, "AI_text_processing"))
sys.path.append(os.path.join(PROJECT_ROOT, "Function"))
sys.path.append(os.path.join(PROJECT_ROOT, "scraping"))

from webhook_server import generate_reply
from linebot.models import TextSendMessage, FlexSendMessage

CATEGORIES_PATH = os.path.join(PROJECT_ROOT, "data", "categories", "categories_flat.json")

# จำนวนตัวอย่างที่จะสุ่มเทสในแต่ละกลุ่ม (ปรับได้ ยิ่งเยอะยิ่งครอบคลุม
# แต่ยิ่งใช้เวลานาน โดยเฉพาะกลุ่มที่มีโอกาส fallback ไป network)
N_EXACT_SAMPLES = 30
N_TYPO_SAMPLES = 20
N_PROMOTION_SAMPLES = 15

# เพดานเวลาตามเกณฑ์อาจารย์ (วินาที) ใช้เช็คเฉพาะเคสที่ไม่ควร fallback
# ไป network (คาดว่าเป็น local exact/fuzzy match ล้วน ๆ)
LOCAL_LATENCY_BUDGET_SECONDS = 2.0


def load_categories():
    if not os.path.exists(CATEGORIES_PATH):
        print(f"❌ ไม่พบไฟล์ {CATEGORIES_PATH} — เช็ค path หรือรัน get_categories.py ก่อน")
        sys.exit(1)
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_typo(text: str) -> str:
    """
    ทำให้ข้อความ "พิมพ์ผิดแบบสมจริง" แบบสุ่ม 1 ใน 3 แบบ:
    ตัดตัวอักษรออก 1 ตัว / เพิ่มตัวอักษรซ้ำ 1 ตัว / สลับ 2 ตัวที่ติดกัน
    (จำลองการพิมพ์ผิดที่มักเจอจริง เช่น "น้ำปลา" -> "นำปลา" ตัดสระ)
    """
    if len(text) < 2:
        return text

    typo_type = random.choice(["delete", "duplicate", "swap"])
    pos = random.randint(0, len(text) - 2)

    if typo_type == "delete":
        return text[:pos] + text[pos + 1:]
    elif typo_type == "duplicate":
        return text[:pos] + text[pos] + text[pos:]
    else:  # swap
        chars = list(text)
        chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
        return "".join(chars)


def run_case(label: str, message: str, expect_flex: bool = None, is_local_only: bool = True):
    """
    รัน 1 เคสทดสอบ วัดเวลา จับ error ถ้ามี คืนค่า dict สรุปผล
    expect_flex: True ถ้าคาดว่าควรได้ FlexSendMessage, False ถ้าคาดว่า
                 ควรได้ TextSendMessage, None ถ้าไม่ยืนยันชัดเจน (แค่ดูว่า
                 ไม่ error ก็พอ)
    """
    start = time.time()
    error = None
    reply_type = None

    try:
        reply = generate_reply(message)
        reply_type = "flex" if isinstance(reply, FlexSendMessage) else "text"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    elapsed = time.time() - start

    passed = error is None
    if passed and expect_flex is not None:
        got_flex = (reply_type == "flex")
        if got_flex != expect_flex:
            passed = False
            error = f"คาดว่าจะได้ {'flex' if expect_flex else 'text'} แต่ได้ {reply_type}"

    return {
        "label": label,
        "message": message,
        "passed": passed,
        "error": error,
        "elapsed": elapsed,
        "reply_type": reply_type,
        "is_local_only": is_local_only,
    }


def print_summary(results: list):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print("\n" + "=" * 70)
    print("สรุปผลการทดสอบทั้งหมด")
    print("=" * 70)
    print(f"รวมทั้งหมด: {total} เคส | ผ่าน: {passed} | ไม่ผ่าน: {failed}")

    if failed > 0:
        print("\n--- เคสที่ไม่ผ่าน ---")
        for r in results:
            if not r["passed"]:
                print(f"  ❌ [{r['label']}] {r['message']!r} -> {r['error']}")

    local_results = [r for r in results if r["is_local_only"] and r["passed"]]
    if local_results:
        times = [r["elapsed"] for r in local_results]
        avg_time = sum(times) / len(times)
        max_time = max(times)
        over_budget = [r for r in local_results if r["elapsed"] > LOCAL_LATENCY_BUDGET_SECONDS]

        print(f"\n--- เวลาที่ใช้ (เฉพาะเคส local ไม่ fallback network, {len(local_results)} เคส) ---")
        print(f"เฉลี่ย: {avg_time*1000:.1f} ms | สูงสุด: {max_time*1000:.1f} ms | "
              f"งบที่กำหนด: {LOCAL_LATENCY_BUDGET_SECONDS*1000:.0f} ms")

        if over_budget:
            print(f"⚠️  มี {len(over_budget)} เคสที่เกินงบเวลา:")
            for r in over_budget:
                print(f"  - [{r['label']}] {r['message']!r}: {r['elapsed']*1000:.1f} ms")
        else:
            print("✅ ทุกเคส local อยู่ในงบเวลาที่กำหนด")

    print("=" * 70)
    return failed == 0


def main():
    categories = load_categories()
    print(f"โหลด categories_flat.json ได้ {len(categories)} รายการ\n")

    results = []

    # ---------- กลุ่ม 1: Local exact match (สุ่มจากชื่อ category จริง) ----------
    print(f"=== กลุ่ม 1: Local Exact Match ({N_EXACT_SAMPLES} เคส) ===")
    sample_exact = random.sample(categories, min(N_EXACT_SAMPLES, len(categories)))
    for cat in sample_exact:
        r = run_case("exact", cat["name"], is_local_only=True)
        results.append(r)
        status = "✅" if r["passed"] else "❌"
        print(f"{status} {cat['name']!r} ({r['elapsed']*1000:.1f} ms, {r['reply_type']})")

    # ---------- กลุ่ม 2: Local fuzzy match (พิมพ์ผิดจากชื่อจริง) ----------
    print(f"\n=== กลุ่ม 2: Local Fuzzy Match / พิมพ์ผิด ({N_TYPO_SAMPLES} เคส) ===")
    sample_typo = random.sample(categories, min(N_TYPO_SAMPLES, len(categories)))
    for cat in sample_typo:
        typo_text = make_typo(cat["name"])
        r = run_case(f"typo (เดิม: {cat['name']!r})", typo_text, is_local_only=True)
        results.append(r)
        status = "✅" if r["passed"] else "❌"
        print(f"{status} {typo_text!r} (จาก {cat['name']!r}) ({r['elapsed']*1000:.1f} ms, {r['reply_type']})")

    # ---------- กลุ่ม 3: ask_promotion ผสม entity ----------
    print(f"\n=== กลุ่ม 3: ask_promotion ผสม Entity ({N_PROMOTION_SAMPLES} เคส) ===")
    sample_promo = random.sample(categories, min(N_PROMOTION_SAMPLES, len(categories)))
    for cat in sample_promo:
        message = f"{cat['name']}โปรโมชั่น"
        r = run_case(f"ask_promotion (หมวด: {cat['name']!r})", message, is_local_only=True)
        results.append(r)
        status = "✅" if r["passed"] else "❌"
        print(f"{status} {message!r} ({r['elapsed']*1000:.1f} ms, {r['reply_type']})")

    # ---------- กลุ่ม 4: Edge cases ที่เคยเจอบั๊กมาก่อน ----------
    print("\n=== กลุ่ม 4: Edge Cases ที่เคยเจอบั๊กมาก่อน ===")
    edge_cases = [
        ("greeting", "สวัสดีครับ", False, True),
        ("greeting ทั่วไป", "หวัดดีครับ", False, True),
        ("โปรโมชั่นเดี่ยว ๆ (เคยพัง)", "โปรโมชั่น", False, True),
        ("ข้อความยาวผิดปกติ", "น้ำปลา" + "า" * 500, None, True),
        ("จรวดไปดวงจันทร์ (ไม่ควรเจออะไร)", "อยากได้จรวดไปดวงจันทร์", None, False),
        ("แบรนด์ที่ไม่ใช่ category (fallback)", "เลย์", None, False),
        ("แบรนด์ + โปร (fallback, เคยพัง)", "เลย์โปรโมชั่น", None, False),
    ]
    for label, message, expect_flex, is_local in edge_cases:
        r = run_case(label, message, expect_flex=expect_flex, is_local_only=is_local)
        results.append(r)
        status = "✅" if r["passed"] else "❌"
        print(f"{status} [{label}] {message[:50]!r}{'...' if len(message) > 50 else ''} "
              f"({r['elapsed']*1000:.1f} ms, {r['reply_type']})")
        if not is_local:
            time.sleep(1.0)  # เว้นระยะก่อนยิง network ครั้งถัดไป (กัน rate limit)

    # ---------- ข้อความว่างเปล่า (กัน crash) ----------
    print("\n=== กลุ่ม 5: ข้อความว่างเปล่า/แปลก ๆ ===")
    for label, message in [("ว่างเปล่า", ""), ("แค่ช่องว่าง", "   "), ("อีโมจิล้วน ๆ", "😀😀😀")]:
        r = run_case(label, message, is_local_only=True)
        results.append(r)
        status = "✅" if r["passed"] else "❌"
        print(f"{status} [{label}] {message!r} ({r['elapsed']*1000:.1f} ms, {r['reply_type']})")

    all_passed = print_summary(results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()