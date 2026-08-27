"""
intent_detector.py
--------------------------------
จับ "Intent" (ผู้ใช้ต้องการอะไร) จากข้อความ ด้วย keyword matching ล้วนๆ
(ไม่ใช้ BERT ในไฟล์นี้ — BERT จะไปอยู่แยกต่างหากสำหรับทำ log เปรียบเทียบ
ตามใบปฏิบัติการ ไม่เกี่ยวกับ flow การตอบ user จริง)

Intent ที่รองรับตอนนี้ (ปรับ/เพิ่มได้ทีหลัง):
- "search_product" : ต้องการหาสินค้า (ค่าเริ่มต้น ถ้าจับ intent อื่นไม่ได้
                      แต่มี entity ที่ match ได้ ก็ยังถือว่าเป็น search_product)
- "ask_promotion"  : ถามเรื่องโปรโมชั่น
- "greeting"       : ทักทาย
- "unknown"        : จับ intent อะไรไม่ได้เลย
"""

# เก็บ keyword แต่ละ intent ไว้เป็น list เพื่อเช็คแบบ "มีคำนี้อยู่ในข้อความไหม"
# (substring match) ไม่ต้องตรงเป๊ะทั้งประโยค
INTENT_KEYWORDS = {
    "greeting": [
        "สวัสดี", "หวัดดี", "ดีครับ", "ดีค่ะ", "hello", "hi",
    ],
    "ask_promotion": [
        "โปร", "โปรโมชั่น", "โปรโมชัน", "ลดราคา", "ส่วนลด", "ดีล",
        "แถม", "ลดกี่บาท", "promotion",
    ],
    # search_product ไม่ต้องมี keyword เฉพาะ เพราะถือเป็นค่าเริ่มต้น
    # (ถ้าไม่เข้าเงื่อนไข intent อื่นเลย และมี entity ที่ match ได้ ให้ถือว่า
    # เป็น search_product โดยอัตโนมัติ ไปดูใน text_processor.py)
}

# ลำดับการเช็ค intent สำคัญ ถ้าข้อความเข้าหลาย intent พร้อมกัน
# จะยึดตามลำดับนี้ (บนสุด = ความสำคัญสูงสุด)
INTENT_PRIORITY = ["greeting", "ask_promotion"]


def detect_intent_with_keyword(text: str):
    """
    เหมือน detect_intent() แต่คืนค่าเป็น tuple (intent, matched_keyword)
    โดย matched_keyword คือคำที่ "ยาวที่สุด" ในบรรดา keyword ของ intent
    นั้นที่เจอในข้อความ (ไม่ใช่แค่ตัวแรกที่เจอ)

    เหตุผลที่ต้องเอา "ยาวที่สุด": ป้องกันปัญหาที่ข้อความสั้น ๆ อย่าง
    "โปรโมชั่น" เดี่ยว ๆ ถูกจับ intent ด้วยคำว่า "โปร" (สั้น) แล้วเหลือ
    "โมชั่น" ไปหา entity ต่อ ซึ่งอาจไปแมทช์มั่วกับชื่อหมวดหมู่ที่บังเอิญ
    มีคำว่า "โมชั่น" ซ้อนอยู่ได้ (เช่น "โปรตีนขายดีและโปรโมชั่น")
    ถ้าตัดคำที่ยาวที่สุดที่ตรงกับ intent ("โปรโมชั่น" ทั้งคำ) ออกไปเลย
    จะเหลือข้อความว่างเปล่า ทำให้รู้ได้ทันทีว่าไม่มี entity อะไรให้หา

    คืนค่า (intent, None) ถ้าไม่เข้าเงื่อนไขไหนเลย
    """
    if not text:
        return "unknown", None

    normalized = text.strip().lower()

    for intent in INTENT_PRIORITY:
        keywords = INTENT_KEYWORDS.get(intent, [])
        matched = [kw for kw in keywords if kw.lower() in normalized]
        if matched:
            longest = max(matched, key=len)
            return intent, longest

    return "unknown", None


def detect_intent(text: str) -> str:
    """
    รับข้อความผู้ใช้ คืนค่า intent (string) เฉย ๆ (เผื่อที่ไหนอยากใช้
    แบบง่าย ไม่สนใจ matched_keyword) ข้างในเรียก detect_intent_with_keyword()
    ตัวเดียวกัน เพื่อไม่ให้ logic สองจุดเพี้ยนไม่ตรงกัน
    """
    intent, _ = detect_intent_with_keyword(text)
    return intent


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    test_cases = [
        "สวัสดีครับ",
        "วันนี้มีโปรโมชั่นอะไรบ้าง",
        "อยากได้น้ำปลา",
        "มีซอสมะเขือเทศไหม",
        "ลดราคาน้ำยาซักผ้าไหม",
    ]
    for t in test_cases:
        print(f"{t!r:40} -> {detect_intent(t)}")