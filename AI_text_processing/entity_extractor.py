"""
entity_extractor.py
--------------------------------
ดึง "Entity" (ประเภทสินค้าที่ผู้ใช้ต้องการ) จากข้อความ โดยจับคู่กับ
รายชื่อ leaf category ที่มีอยู่แล้วใน data/categories/categories_flat.json
(833 รายการ จาก get_categories.py)

--------------------------------
บันทึกการออกแบบ (สำคัญ อ่านก่อนแก้โค้ดส่วนนี้)
--------------------------------
ลองมาแล้ว 2 วิธีที่ "ดูดี" แต่พังจริงตอนทดสอบ:

วิธีที่ 1 - "exact match ก่อน เจอแล้วหยุดเลย": พังตรงที่คำสั้น ๆ
(เช่น "ปลา") บังเอิญเป็น substring ของข้อความที่พิมพ์ผิดจนคำที่ตั้งใจ
จริง (เช่น "น้ำปลา" พิมพ์ตกวรรณยุกต์ ้ กลายเป็น "นำปลา") ไม่ match
แบบ exact เลย ระบบเลยตอบผิดหมวดหมู่ไปเลย (ตอบ "ปลา" สด ทั้งที่ user
ต้องการ "น้ำปลา")

วิธีที่ 2 - "ถ่วงคะแนนด้วยความยาวชื่อ" (score × len หรือ score + len):
คิดว่าจะแก้วิธีที่ 1 ได้ เพราะให้ชื่อยาว/เจาะจงกว่ามีสิทธิ์ชนะชื่อสั้น
ที่ตรงเป๊ะแบบบังเอิญ แต่กลับพังคนละแบบ: ชื่อยาวที่ "คล้ายเฉย ๆ" (ไม่ได้
match เป๊ะ) กลับไปเอาชนะชื่อสั้นที่ match ตรงเป๊ะ 100% ได้ เพราะตัวเลข
ความยาวไปครอบคะแนนความคล้ายจนเพี้ยน (ทดสอบแล้วพังจริง เช่น
"ขอดูน้ำยาซักผ้าหน่อย" ควรได้ "น้ำยาซักผ้า" (exact เป๊ะ) แต่ระบบดันเลือก
"น้ำยาซักผ้าและทำความสะอาดเด็ก" ที่คล้ายแค่ 71% เพราะชื่อยาวกว่ามาก)

--------------------------------
วิธีที่ใช้จริง (ทดสอบแล้วผ่านทุกเคส): "Superset Detection"
--------------------------------
แทนที่จะพยายามคิดสูตรคะแนนเดียวที่ใช้ได้กับทุกคู่ชื่อ (ซึ่งพังทั้ง 2
รอบที่ลอง) ให้แก้แบบเจาะจงตรงจุดที่มีปัญหาจริงแทน:

1. Exact substring match ก่อนเหมือนเดิม (เร็ว แม่นสุดถ้า match ได้)
   ถ้ามีหลายชื่อ match พร้อมกัน เลือกชื่อที่ "ยาวที่สุด" (เจาะจงสุด)
2. เตรียมข้อมูลไว้ล่วงหน้า (ตอนโหลด vocabulary ครั้งเดียว) ว่าชื่อไหน
   เป็น "ส่วนหนึ่ง" ของชื่ออื่นบ้าง (เช่น "ปลา" เป็นส่วนหนึ่งของ
   "น้ำปลา") เรียกว่า supersets
3. พอ exact match เจอชื่อสั้น ก่อนจะตอบเลย ให้เช็คก่อนว่ามีชื่อยาวกว่า
   ที่ "มีชื่อสั้นนี้ซ่อนอยู่" ไหม ถ้ามี ลอง fuzzy เทียบข้อความทั้งประโยค
   กับชื่อยาวนั้นโดยเฉพาะ (ไม่ใช่เทียบกับทุกชื่อทั้ง 833 แบบสุ่ม) ถ้า
   คะแนนสูงพอ (>= UPGRADE_SCORE_THRESHOLD) ค่อย "อัปเกรด" ไปใช้ชื่อยาว
   แทน เพราะน่าจะเป็นกรณีพิมพ์ผิดจนพลาดชื่อที่ถูกต้อง

ข้อดีของวิธีนี้: การเปรียบเทียบเกิดขึ้นเฉพาะระหว่าง "คู่ชื่อที่มีความ
สัมพันธ์กันจริง ๆ" (ชื่อหนึ่งซ่อนอยู่ในอีกชื่อ) ไม่ใช่เทียบทุกชื่อกับ
ทุกชื่อแบบสุ่มด้วยสูตรเดียว จึงไม่มีทางที่ชื่อยาวที่ "ไม่เกี่ยวกันเลย"
จะมาแย่งชนะชื่อสั้นที่ตรงเป๊ะได้ (ตามที่วิธีที่ 2 พังไป)

ถ้าไม่มี exact match เลย ค่อย fallback ไปลอง fuzzy กับทุกชื่อใน
vocabulary ตามปกติ (เผื่อกรณีพิมพ์ผิดหนักจนไม่เหลือ substring ตรง ๆ
เลยสักคำ)
"""

import json
import os

try:
    from rapidfuzz import fuzz, process as rf_process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    # เผื่อเครื่องยังไม่ได้ pip install rapidfuzz จะได้ไม่ crash ทั้งระบบ
    # (แต่ fuzzy matching จะถูกข้ามไปโดยอัตโนมัติ เหลือแค่ exact match)
    RAPIDFUZZ_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_PATH = os.path.join(SCRIPT_DIR, "..", "data", "categories", "categories_flat.json")

# เกณฑ์คะแนน fuzzy (0-100) ขั้นต่ำตอน "ไม่มี exact match เลยสักคำ"
# (fallback สุดท้าย ค้นทุกชื่อใน vocabulary)
#
# --- บันทึกการปรับครั้งที่ 2: 85 -> 80 ---
# ตอนแรกปรับจาก 75 เป็น 85 เพราะเจอบั๊ก "ถั่ว/มั่ว" (ดูบันทึกด้านล่าง)
# แต่พอใช้งานจริงเจอเคส "นำดืม" (พิมพ์ตกสระ "น้ำดื่ม") ได้คะแนนพอดี 80.0
# ไม่ผ่านเกณฑ์ 85 ทั้งที่เป็นคำพิมพ์ผิดที่สมเหตุสมผล ตรวจสอบแล้วว่าลดเป็น
# 80 ยังปลอดภัย เพราะเคส "ถั่ว/มั่ว" ที่เคยพัง (คะแนน 75.0) ยังต่ำกว่า 80
# อยู่ (เหลือ margin กันไว้ 5 คะแนน แคบกว่าเดิมที่เคยมี 10 คะแนน แต่ยังปลอดภัย)
#
# ข้อควรรู้: การปรับนี้ "ไม่ได้" แก้คำพิมพ์ผิดทุกแบบ เช่น "นำสม" (น้ำส้ม)
# ยังได้แค่ 75.0 เท่ากับเคสบั๊กเดิมเป๊ะ ไม่ผ่านแม้จะลดเป็น 80 แล้วก็ตาม
# (เป็นข้อจำกัดที่ยอมรับไว้ ไม่ใช่ทุกคำพิมพ์ผิดจะ fuzzy match ได้เสมอไป)
FUZZY_SCORE_THRESHOLD = 80

# เกณฑ์คะแนนขั้นต่ำสำหรับ "อัปเกรด" จากชื่อสั้นที่ exact match ไปชื่อยาว
# ที่เจาะจงกว่า
UPGRADE_SCORE_THRESHOLD = 85


def load_categories():
    """โหลด leaf category list จาก categories_flat.json"""
    if not os.path.exists(CATEGORIES_PATH):
        print(f"[entity_extractor] ไม่พบไฟล์ {CATEGORIES_PATH}")
        return []
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_supersets(categories):
    """
    สร้าง mapping: {ชื่อสั้น: [รายชื่อชื่อยาวที่ 'มีชื่อสั้นนี้ซ่อนอยู่']}
    ทำครั้งเดียวตอนโหลด vocabulary (O(n²) แต่ n=833 เล็กพอ ไม่กระทบ
    performance ตอน runtime เลย เพราะทำแค่ครั้งเดียวตอน import โมดูล)
    """
    supersets = {}
    for c1 in categories:
        name1 = c1["name"].strip()
        if not name1:
            continue
        for c2 in categories:
            if c1["id"] == c2["id"]:
                continue
            name2 = c2["name"].strip()
            if name1 and name1 != name2 and name1 in name2:
                supersets.setdefault(name1, []).append(name2)
    return supersets


# โหลด/เตรียมข้อมูลครั้งเดียวตอน import โมดูล
_CATEGORIES = load_categories()
_CATEGORY_NAMES = [c["name"] for c in _CATEGORIES]
_SUPERSETS = build_supersets(_CATEGORIES)


def _exact_matches(text: str):
    """
    หาทุก category ที่ชื่อเป็น substring ของข้อความ (หรือข้อความสั้น ๆ
    ตรงกับชื่อพอดี) เรียงจากชื่อยาวสุด (เจาะจงสุด) ไปสั้นสุด
    """
    matches = []
    for cat in _CATEGORIES:
        name = cat["name"].strip()
        if not name:
            continue
        if name in text or text.strip() == name:
            matches.append(cat)
    matches.sort(key=lambda c: len(c["name"]), reverse=True)
    return matches


def _try_upgrade(text: str, best_cat: dict):
    """
    เช็คว่าจากชื่อที่ exact match ได้ (best_cat) มีชื่อยาวกว่าที่ 'ซ่อน'
    ชื่อนี้อยู่ไหม (จาก _SUPERSETS ที่เตรียมไว้แล้ว) ถ้ามี ลอง fuzzy
    เทียบข้อความกับชื่อยาวนั้นโดยเฉพาะ ถ้าคะแนนสูงพอ คืน category ของ
    ชื่อยาวนั้นแทน (พร้อมคะแนน) ถ้าไม่เข้าเงื่อนไข คืน None
    """
    candidate_names = _SUPERSETS.get(best_cat["name"], [])

    if not candidate_names:
        # ไม่มีชื่อยาวไหนซ่อนชื่อนี้อยู่เลย -> ไม่มีอะไรให้ fuzzy เทียบ
        # (ไม่ต้อง print เพราะเคสนี้เกิดบ่อยมาก จะรก log เปล่า ๆ)
        return None

    print(f"[entity_extractor] exact match ได้ {best_cat['name']!r} "
          f"แต่มีชื่อยาวกว่าที่เกี่ยวข้อง {candidate_names} -> ลอง fuzzy เทียบเพื่ออัปเกรด")

    if not RAPIDFUZZ_AVAILABLE:
        print("[entity_extractor] rapidfuzz ไม่พร้อมใช้งาน -> ข้ามการอัปเกรด")
        return None

    best_upgrade = None
    best_score = 0.0
    for name in candidate_names:
        score = fuzz.partial_ratio(text, name)
        print(f"[entity_extractor]   fuzzy เทียบกับ {name!r} -> score={score:.1f}")
        if score > best_score:
            best_score = score
            best_upgrade = name

    if best_upgrade is None or best_score < UPGRADE_SCORE_THRESHOLD:
        print(f"[entity_extractor] คะแนนอัปเกรดสูงสุด={best_score:.1f} ไม่ถึงเกณฑ์ "
              f"({UPGRADE_SCORE_THRESHOLD}) -> ใช้ผล exact match เดิม ({best_cat['name']!r})")
        return None

    print(f"[entity_extractor] อัปเกรดสำเร็จ: {best_cat['name']!r} -> {best_upgrade!r} "
          f"(score={best_score:.1f})")

    # หา category dict เต็ม ๆ จากชื่อที่อัปเกรดไป
    for cat in _CATEGORIES:
        if cat["name"] == best_upgrade:
            return {"category": cat, "score": best_score}
    return None


def _fallback_fuzzy_match(text: str):
    """
    ใช้เมื่อไม่มี exact match เลยสักคำ (กรณีพิมพ์ผิดหนักมาก) ลอง fuzzy
    เทียบกับทุกชื่อใน vocabulary
    """
    print(f"[entity_extractor] ไม่มี exact match เลยสักคำ -> fallback ไป fuzzy "
          f"เทียบกับทุก {len(_CATEGORY_NAMES)} ชื่อใน vocabulary")

    if not RAPIDFUZZ_AVAILABLE:
        print("[entity_extractor] rapidfuzz ไม่พร้อมใช้งาน -> ข้าม fuzzy match ทั้งหมด")
        return None
    if not _CATEGORY_NAMES:
        print("[entity_extractor] vocabulary ว่างเปล่า -> ข้าม fuzzy match")
        return None

    best = rf_process.extractOne(text, _CATEGORY_NAMES, scorer=fuzz.partial_ratio)
    if best is None:
        print("[entity_extractor] fuzzy fallback: ไม่เจอผลลัพธ์เลย")
        return None

    matched_name, score, index = best
    print(f"[entity_extractor] fuzzy fallback คะแนนสูงสุด: {matched_name!r} "
          f"(score={score:.1f}, threshold={FUZZY_SCORE_THRESHOLD})")

    if score < FUZZY_SCORE_THRESHOLD:
        print("[entity_extractor] คะแนนไม่ถึงเกณฑ์ -> ถือว่าไม่เจอ")
        return None

    print(f"[entity_extractor] fuzzy fallback ผ่านเกณฑ์ -> ใช้ผลนี้ (category_id={_CATEGORIES[index]['id']})")
    return {"category": _CATEGORIES[index], "score": score}


def extract_entity(text: str):
    """
    รับข้อความผู้ใช้ คืนค่าเป็น dict บอกผลลัพธ์การจับ entity:
        {
            "found": True/False,
            "match_type": "exact" | "exact_upgraded" | "fuzzy" | "none",
            "raw_score": ... (คะแนนดิบ 0-100 เผื่ออยาก debug/log),
            "category_id": ... หรือ None,
            "category_name": ... หรือ None,
            "breadcrumb": [...] หรือ None,
        }
    """
    empty_result = {
        "found": False, "match_type": "none", "raw_score": 0,
        "category_id": None, "category_name": None, "breadcrumb": None,
    }

    if not text or not text.strip() or not _CATEGORIES:
        print("[entity_extractor] ข้อความว่างเปล่า หรือ vocabulary ว่าง -> ข้ามการค้นหาทั้งหมด")
        return empty_result

    # ---------- ขั้นที่ 1: exact substring match ----------
    exact = _exact_matches(text)

    if exact:
        best = exact[0]  # ชื่อยาวสุดที่ match แบบ exact

        # ---------- ขั้นที่ 1.5: ลองอัปเกรดไปชื่อที่เจาะจงกว่า ----------
        # *** ยกเว้น *** ถ้าข้อความที่ user พิมพ์ "ตรงกับชื่อ category
        # เป๊ะ ๆ ทั้งประโยค" (ไม่ใช่แค่ตรงบางส่วน) แปลว่ามั่นใจสูงสุด
        # อยู่แล้ว ไม่มีเหตุผลต้องลองอัปเกรดเลย เพราะ fuzz.partial_ratio
        # จะให้คะแนนเต็ม 100 เสมอถ้าข้อความสั้นเป็น substring ของชื่อ
        # ยาวกว่า (เช่น "น้ำปลา" เป็นส่วนหนึ่งของ "น้ำปลาหวาน" ที่ซ้อนอยู่
        # ใน "พริกเกลือ น้ำปลาหวาน") ทำให้อัปเกรดผิดไปเป็นสินค้าคนละ
        # อย่างกันเลยทั้งที่ไม่เกี่ยวข้องกัน การอัปเกรดควรมีไว้เฉพาะกรณี
        # exact match เจอแค่ "บางส่วน" ของข้อความที่ยาวกว่า (เช่น
        # "นำปลาา มีมั้ย" ที่ exact เจอแค่ "ปลา" สั้น ๆ เพราะพิมพ์ผิด)
        if text.strip() == best["name"]:
            print(f"[entity_extractor] ข้อความตรงกับ {best['name']!r} เป๊ะทั้งประโยค "
                  f"-> มั่นใจสูงสุดอยู่แล้ว ข้ามการลองอัปเกรดไปเลย")
            upgrade = None
        else:
            upgrade = _try_upgrade(text, best)

        if upgrade:
            cat = upgrade["category"]
            print(f"[entity_extractor] สรุป: ใช้ fuzzy (อัปเกรดจาก exact) -> {cat['name']!r}\n")
            return {
                "found": True,
                "match_type": "exact_upgraded",
                "raw_score": round(upgrade["score"], 1),
                "category_id": cat["id"],
                "category_name": cat["name"],
                "breadcrumb": cat["breadcrumb"],
            }

        print(f"[entity_extractor] สรุป: ใช้ exact match ล้วน ๆ ไม่ได้แตะ fuzzy เลย -> {best['name']!r}\n")
        return {
            "found": True,
            "match_type": "exact",
            "raw_score": 100.0,
            "category_id": best["id"],
            "category_name": best["name"],
            "breadcrumb": best["breadcrumb"],
        }

    # ---------- ขั้นที่ 2: ไม่มี exact match เลย -> fallback fuzzy ----------
    fallback = _fallback_fuzzy_match(text)
    if fallback:
        cat = fallback["category"]
        print(f"[entity_extractor] สรุป: ใช้ fuzzy (fallback เต็มรูปแบบ) -> {cat['name']!r}\n")
        return {
            "found": True,
            "match_type": "fuzzy",
            "raw_score": round(fallback["score"], 1),
            "category_id": cat["id"],
            "category_name": cat["name"],
            "breadcrumb": cat["breadcrumb"],
        }

    print("[entity_extractor] สรุป: ลองทั้ง exact และ fuzzy แล้วไม่เจอเลย\n")
    return empty_result


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    print(f"โหลด category ได้ {len(_CATEGORIES)} รายการ")
    print(f"rapidfuzz พร้อมใช้งาน: {RAPIDFUZZ_AVAILABLE}\n")

    test_cases = [
        "อยากได้น้ำปลา",           # ควร exact "น้ำปลา"
        "มีซอสมะเขือเทศไหม",        # ควร exact "ซอสมะเขือเทศ"
        "นำปลาา มีมั้ย",            # พิมพ์ผิด ควร exact_upgraded -> "น้ำปลา"
        "ขอดูน้ำยาซักผ้าหน่อย",      # ควร exact "น้ำยาซักผ้า" (ไม่ใช่ตัวยาว)
        "น้ำยาซักผ้ามีโปรไหม",       # ควร exact "น้ำยาซักผ้า"
        "มีปลาทูขายไหม",            # ควร exact "ปลา" (ไม่ควรถูกอัปเกรดผิด)
        "อยากได้จรวดไปดวงจันทร์",    # ไม่ควร match อะไรเลย
    ]
    for t in test_cases:
        result = extract_entity(t)
        print(f"{t!r}")
        print(f"  -> {result}\n")