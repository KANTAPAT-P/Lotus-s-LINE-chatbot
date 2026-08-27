"""
text_processor.py
--------------------------------
Entry point หลักของ AI_text_processing รวม intent_detector.py และ
entity_extractor.py เข้าด้วยกัน เป็นจุดเดียวที่ webhook_server.py
ต้อง import ไปใช้ (ไฟล์อื่นในโฟลเดอร์นี้ถือเป็น implementation detail
ข้างในไม่ต้องยุ่งจากภายนอก)

ตรรกะการตัดสินใจ intent สุดท้าย:
- ถ้า keyword เจอ intent ชัดเจน (greeting / ask_promotion) -> ใช้ตามนั้น
  (แต่ยังพยายามดึง entity ควบคู่ไปด้วย เผื่อเป็นคำสั่งรวม เช่น
  "น้ำยาซักผ้ามีโปรไหม" -> intent=ask_promotion แต่ก็มี entity ติดมา)
- ถ้า keyword ไม่เจอ intent ไหนเลย (unknown) แต่ดึง entity ได้
  -> ถือว่าเป็น "search_product" โดยอัตโนมัติ (ค่าเริ่มต้นตามที่ออกแบบไว้)
- ถ้าทั้ง intent และ entity ไม่เจอเลย -> คงเป็น "unknown"
  (ให้ webhook_server.py ตอบ fallback message)

--------------------------------
บันทึกการแก้บั๊ก: "โปรโมชั่น" เดี่ยว ๆ ไปแมทช์ผิดกับ
"โปรตีนขายดีและโปรโมชั่น"
--------------------------------
สาเหตุ: fuzz.partial_ratio ให้คะแนนเต็ม 100 เสมอถ้าข้อความสั้นเป็น
substring ของข้อความยาว ไม่ว่าข้อความยาวจะมีความหมายเกี่ยวข้องกันจริง
หรือไม่ก็ตาม ("โปรโมชั่น" เป็น substring ท้ายชื่อ "โปรตีนขายดีและ
โปรโมชั่น" พอดี) ทำให้ entity_extractor เข้าใจผิดว่าเจอ entity ทั้งที่
จริง ๆ คำว่า "โปรโมชั่น" ควรถูกตีความเป็นแค่ intent keyword เท่านั้น
ไม่ใช่ชื่อสินค้า

วิธีแก้: ก่อนส่งข้อความไปหา entity ให้ "ตัดคำที่เป็น intent keyword
ออกก่อน" (ใช้คำที่ยาวที่สุดที่ match เพื่อตัดให้หมดจด) แล้วค่อยเอา
ส่วนที่เหลือไปหา entity ถ้าตัดแล้วไม่เหลืออะไรเลย (เช่น "โปรโมชั่น"
เดี่ยว ๆ ตัด "โปรโมชั่น" ออกจะเหลือค่าว่าง) ก็ไม่ต้องไปหา entity เลย
เพราะไม่มีอะไรให้หาแล้วจริง ๆ

--------------------------------
บันทึกการแก้บั๊กรอบ 2: "โปรโมชั่นนนนนนนนนนนนนนนน" (พิมพ์เน้นเสียง)
ทำให้ fallback ไปค้นสดด้วยคำมั่ว ๆ
--------------------------------
เจอจากการทดสอบผ่าน LINE จริง: user พิมพ์ "โปรโมชั่นนนนนนนนนนนนนนนน"
(เติม "น" ซ้ำท้ายคำเพื่อเน้นเสียง ตามสไตล์การพิมพ์แชทของคนไทย) พอตัด
"โปรโมชั่น" (intent keyword) ออก จะเหลือ "นนนนนนนนนนนนนนน" ซึ่ง "ไม่ว่าง
เปล่า" ในทางเทคนิค (ผ่านเงื่อนไข `if matched_keyword and not
entity_search_text` เดิมไปได้) แต่ก็ไม่มีความหมายอะไรเหมือนกัน ระบบเลย
เข้าใจผิดว่าเป็นคำค้นที่มีความหมาย ส่งไป fallback ค้นสดที่ Lotus's ด้วย
คำว่า "นนนนนนนนนนนนนนน" ซึ่ง Lotus's เองก็คืนสินค้าไม่เกี่ยวข้องกลับมา
(ปัญหาเดิมที่เคยเจอกับคำมั่ว ๆ อื่น ๆ)

วิธีแก้: เพิ่มการเช็ค "ข้อความที่เหลือเป็นตัวอักษรเดียวกันซ้ำล้วน ๆ
ไหม" (เช่น "นนนนน", "าาาาา") ถ้าใช่ ให้ถือว่าเป็น "ขยะจากการพิมพ์เน้น
เสียง" เหมือนกับกรณีว่างเปล่า ข้ามการหา entity และเคลียร์
entity_search_text ทิ้งด้วย กัน webhook_server.py เอาไป fallback ค้นสด
ด้วยคำมั่ว ๆ นี้ต่อ
"""

import re

from intent_detector import detect_intent_with_keyword
from entity_extractor import extract_entity

_EMPTY_ENTITY = {
    "found": False, "match_type": "none", "raw_score": 0,
    "category_id": None, "category_name": None, "breadcrumb": None,
}

# ข้อความที่เป็น "ตัวอักษรเดียวกันซ้ำล้วน ๆ" (เช่น "นนนนน", "าาาาา")
# ถือว่าไม่มีความหมาย (มักเป็นการพิมพ์เน้นเสียงต่อท้ายคำเดิม ไม่ใช่
# คำใหม่ที่ตั้งใจพิมพ์) ต้องมีความยาวอย่างน้อย 2 ตัวอักษรถึงจะเข้าเงื่อนไข
# (1 ตัวอักษรเดี่ยว ๆ ปล่อยผ่านไปให้ entity_extractor ตัดสินใจตามปกติ)
_NOISE_PATTERN = re.compile(r"^(.)\1+$")


def _is_noise_text(text: str) -> bool:
    """เช็คว่าข้อความเป็นตัวอักษรเดียวกันซ้ำล้วน ๆ ไหม (ไร้ความหมาย)"""
    return bool(_NOISE_PATTERN.match(text.strip()))


def _strip_matched_keyword(text: str, matched_keyword: str) -> str:
    """
    ตัด matched_keyword ออกจาก text (ตัวแรกที่เจอ, ไม่สนตัวพิมพ์เล็ก-ใหญ่)
    คืนข้อความที่เหลือ (ตัดช่องว่างหัว-ท้ายออกด้วย)
    """
    if not matched_keyword:
        return text
    pattern = re.escape(matched_keyword)
    remainder = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
    return remainder.strip()


def process_message(text: str) -> dict:
    """
    รับข้อความดิบจากผู้ใช้ (LINE message) คืนค่าเป็น dict สรุปผลทั้งหมด
    ที่ webhook_server.py เอาไปตัดสินใจต่อได้เลย:

        {
            "raw_text": "อยากได้น้ำปลา",
            "intent": "search_product",
            "entity": {
                "found": True,
                "match_type": "exact",
                "category_id": 98345,
                "category_name": "น้ำปลา",
                "breadcrumb": ["อาหารแห้งและเครื่องปรุง", "ซอสปรุงรสและทำอาหาร", "น้ำปลา"],
            },
        }
    """
    intent, matched_keyword = detect_intent_with_keyword(text)

    # ---------- greeting ไม่มีทางมี entity ปนมาจริงในทางปฏิบัติ ----------
    # (ไม่มีใครพิมพ์ "สวัสดีน้ำปลาครับ") ต่างจาก ask_promotion ที่เป็น
    # คำสั่งรวมได้จริง (เช่น "น้ำยาซักผ้ามีโปรไหม") จึงข้ามการหา entity
    # ไปเลยทันทีที่เจอ greeting กันคำลงท้ายทั่วไป (เช่น "ครับ", "ค่ะ" ที่
    # เหลือจากการตัด "สวัสดี" ออก) ไปแมทช์มั่วกับ vocabulary โดยไม่ตั้งใจ
    if intent == "greeting":
        print(f"[text_processor] intent=greeting -> ข้ามการหา entity ไปเลย (ไม่มีทางมี entity ปนมาจริง)")
        entity = dict(_EMPTY_ENTITY)
        return {"raw_text": text, "intent": intent, "entity": entity, "entity_search_text": ""}

    # ---------- ตัด intent keyword ออกก่อน ค่อยหา entity จากส่วนที่เหลือ ----------
    entity_search_text = _strip_matched_keyword(text, matched_keyword)

    # เช็คว่าที่เหลือเป็น "ขยะไร้ความหมาย" ไหม (ตัวอักษรซ้ำล้วน ๆ จาก
    # การพิมพ์เน้นเสียง เช่น "นนนนน") ถ้าใช่ ให้เคลียร์ทิ้งเหมือนว่างเปล่า
    if matched_keyword and entity_search_text and _is_noise_text(entity_search_text):
        print(f"[text_processor] ตัด intent keyword {matched_keyword!r} ออกจาก '{text}' "
              f"แล้วเหลือแต่ตัวอักษรซ้ำไร้ความหมาย ({entity_search_text!r}) -> ถือว่าว่างเปล่า")
        entity_search_text = ""

    if matched_keyword and not entity_search_text:
        # ตัด keyword ออกแล้วไม่เหลืออะไรเลย (หรือเหลือแต่ขยะ) -> ไม่มี
        # entity ให้หาจริง ๆ (เช่น "โปรโมชั่น" เดี่ยว ๆ) ข้ามการเรียก
        # extract_entity() ไปเลย
        print(f"[text_processor] ตัด intent keyword {matched_keyword!r} ออกจาก '{text}' "
              f"แล้วไม่เหลือข้อความ -> ข้ามการหา entity")
        entity = dict(_EMPTY_ENTITY)
    else:
        entity = extract_entity(entity_search_text)

    # ---------- print บอกให้เห็นชัด ๆ ว่าตอนนี้ entity ถูก match ด้วยวิธีไหน ----------
    if entity["match_type"] in ("exact", "exact_upgraded"):
        print(f"[text_processor] EXACT match: '{text}' -> '{entity['category_name']}'")
    elif entity["match_type"] == "fuzzy":
        print(f"[text_processor] FUZZY match ใช้งาน!: '{text}' -> '{entity['category_name']}' "
              f"(exact ไม่เจอ เลยใช้ fuzzy แทน)")
    else:
        print(f"[text_processor] ไม่ match เลยทั้ง exact และ fuzzy: '{text}'")

    # ถ้า keyword จับ intent ไม่ได้เลย แต่ entity เจอ -> ถือเป็นการหาสินค้า
    if intent == "unknown" and entity["found"]:
        intent = "search_product"

    return {
        "raw_text": text,
        "intent": intent,
        "entity": entity,
        # ข้อความที่เหลือหลังตัด intent keyword ออกแล้ว (เช่น "เลย์"
        # จาก "เลย์โปรโมชั่น") เอาไว้ให้ webhook_server.py ใช้เป็น
        # keyword ตอน fallback ไป scrap_current_product.py กรณี entity
        # หาไม่เจอใน local vocabulary (เช่นเป็นชื่อแบรนด์ ไม่ใช่ชื่อหมวด)
        # ถ้าเป็นขยะไร้ความหมายจะถูกเคลียร์เป็น "" ไว้แล้วด้านบน กัน
        # fallback ไปค้นสดด้วยคำมั่ว ๆ
        "entity_search_text": entity_search_text,
    }


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    test_cases = [
        "สวัสดีครับ",
        "วันนี้มีโปรโมชั่นอะไรบ้าง",
        "อยากได้น้ำปลา",
        "มีซอสมะเขือเทศไหม",
        "นำปลาา มีมั้ย",
        "น้ำยาซักผ้ามีโปรไหม",
        "อยากได้จรวดไปดวงจันทร์",
        "โปรโมชั่น",                        # เคสที่เจอบั๊กรอบแรก
        "โปร",                              # เคสสั้นกว่านั้นอีก เดี่ยว ๆ ล้วน ๆ
        "มีโปรน้ำยาซักผ้าไหม",               # เคสรวม intent+entity แบบสลับตำแหน่ง
        "โปรโมชั่นนนนนนนนนนนนนนนน",          # เคสที่เจอบั๊กรอบ 2 (พิมพ์เน้นเสียง)
        "น้ำยาซักผ้ามีโปรมั้ยยยยยยยย",        # เคสคล้ายกัน แต่มี entity จริงติดมาด้วย
    ]
    for t in test_cases:
        result = process_message(t)
        print(f"ข้อความ: {t!r}")
        print(f"  intent = {result['intent']}")
        print(f"  entity = {result['entity']}")
        print(f"  entity_search_text = {result['entity_search_text']!r}")
        print()