"""
lotus_searching.py
--------------------------------
ค้นหาสินค้าจาก "ข้อมูลที่ scrape เก็บไว้แล้ว" ใน data/all_product/
(ไม่ใช่ scrape สดจากเว็บ lotus's — อันนั้นเป็นหน้าที่ของ
scrap_current_product.py ที่ใช้เป็น fallback เท่านั้น)

หน้าที่หลัก: รับ category_id ที่ entity_extractor.py จับได้ (จากข้อความ
ผู้ใช้) แล้วไปเปิดไฟล์ data/all_product/<id>_<slug>.json ที่ตรงกัน
คืนรายการสินค้าในหมวดนั้นออกมา

หมายเหตุสำคัญ:
- ไม่ต้องรู้ "slug" เป๊ะตอนค้นหาไฟล์ เพราะหาแบบ "ไฟล์ที่ชื่อขึ้นต้น
  ด้วย <category_id>_" แทน (กันกรณี category_id ตรงแต่จำ slug ผิด)
- ทุก leaf category ควรมีไฟล์อยู่แล้วเสมอ (scrap_all_product.py เขียน
  ไฟล์ให้ทุกหมวดแม้จะไม่มีสินค้าเลยก็ตาม เพราะ resumable logic เช็คจาก
  "มีไฟล์หรือยัง" ไม่ใช่ "มีสินค้าหรือยัง") ถ้าหาไฟล์ไม่เจอเลยถือว่า
  ผิดปกติ (status="error") ไม่ใช่กรณีปกติของ "ของหมด"
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALL_PRODUCT_DIR = os.path.join(SCRIPT_DIR, "..", "data", "all_product")


def _find_category_file(category_id):
    """
    หาไฟล์ JSON ของหมวดหมู่นั้นใน data/all_product/ โดยหาไฟล์ที่ชื่อ
    ขึ้นต้นด้วย "<category_id>_" (ตามรูปแบบที่ scrap_all_product.py
    ตั้งชื่อไว้ เช่น 98345_fish-sauce.json)
    คืน path เต็มถ้าเจอ หรือ None ถ้าไม่เจอ
    """
    if not os.path.isdir(ALL_PRODUCT_DIR):
        print(f"[lotus_searching] ไม่พบโฟลเดอร์ {ALL_PRODUCT_DIR} "
              f"— รัน scrap_all_product.py ก่อนนะ")
        return None

    prefix = f"{category_id}_"
    for filename in os.listdir(ALL_PRODUCT_DIR):
        if filename.startswith(prefix) and filename.endswith(".json"):
            return os.path.join(ALL_PRODUCT_DIR, filename)

    return None


def search_by_category_id(category_id):
    """
    รับ category_id (int) คืนค่าเป็น dict เสมอ:
        {
            "status": "found" | "not_found" | "error",
            "products": [...],
            "category_name": ... หรือ None,
            "breadcrumb": [...] หรือ None,
        }

    ความหมายของแต่ละ status:
    - "found"     : เจอไฟล์ และมีสินค้าอย่างน้อย 1 รายการ
    - "not_found" : เจอไฟล์ แต่ product_count = 0 (หมวดนี้ scrape แล้ว
                    ไม่มีสินค้าขายอยู่จริง ๆ ไม่ใช่ความผิดพลาดของระบบ)
    - "error"     : หาไฟล์ไม่เจอเลย หรืออ่านไฟล์ไม่สำเร็จ (ผิดปกติ
                    เพราะ scrap_all_product.py ควรเขียนไฟล์ให้ทุก
                    leaf category ไว้อยู่แล้ว)
    """
    filepath = _find_category_file(category_id)

    if filepath is None:
        print(f"[lotus_searching] ไม่พบไฟล์สำหรับ category_id={category_id} "
              f"(ผิดปกติ — เช็คว่า category_id ถูกไหม หรือยังไม่ได้ scrape หมวดนี้)")
        return {"status": "error", "products": [], "category_name": None, "breadcrumb": None}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[lotus_searching] อ่านไฟล์ {filepath} ไม่สำเร็จ: {e}")
        return {"status": "error", "products": [], "category_name": None, "breadcrumb": None}

    products = data.get("products", [])
    status = "found" if products else "not_found"

    result = {
        "status": status,
        "products": products,
        "category_name": data.get("category_name"),
        "breadcrumb": data.get("breadcrumb"),
    }

    print(f"[lotus_searching] category_id={category_id} ({result['category_name']!r}) "
          f"-> status={status} ({len(products)} รายการ)")
    return result


def search_from_entity(entity: dict):
    """
    เอาไว้ต่อจากผลลัพธ์ของ entity_extractor.py / text_processor.py
    โดยตรง รับ entity dict ที่ได้จาก extract_entity() (มี found,
    category_id, ...) แล้วค้นหาต่อให้เลย

    เพิ่ม status "no_entity" สำหรับกรณีที่ entity_extractor จับ entity
    ไม่ได้เลยตั้งแต่ต้น (คนละความหมายกับ "not_found" ที่แปลว่า จับ
    entity ได้ แต่ของในหมวดนั้นหมด/ไม่มี) เพื่อให้ webhook_server.py
    เลือกข้อความตอบ user ได้ตรงสถานการณ์กว่า
    """
    if not entity or not entity.get("found"):
        print("[lotus_searching] entity ไม่เจอเลย -> ข้ามการค้นหาไฟล์")
        return {"status": "no_entity", "products": [], "category_name": None, "breadcrumb": None}

    return search_by_category_id(entity["category_id"])


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    print(f"ALL_PRODUCT_DIR = {ALL_PRODUCT_DIR}\n")

    # เคสสมมติ: category_id ที่มีสินค้าจริง (ต้องมีไฟล์อยู่ก่อน ลองรัน
    # scrap_all_product.py ให้เสร็จ แล้วเปลี่ยนเลขนี้เป็น category_id
    # ของหมวดที่รู้ว่ามีของแน่ ๆ เช่น จากตัวอย่าง "น้ำปลา" id=98345)
    test_ids = [98345, 999999999]  # อันหลังคือ id มั่ว ๆ ทดสอบเคส error

    for cid in test_ids:
        print(f"=== ทดสอบ category_id={cid} ===")
        result = search_by_category_id(cid)
        print(f"status: {result['status']}")
        if result["products"]:
            print(f"ตัวอย่างสินค้า: {result['products'][0].get('name')}")
        print()

    # เคสทดสอบ search_from_entity() ต่อจาก entity_extractor.py โดยตรง
    print("=== ทดสอบ search_from_entity() ===")
    fake_entity_found = {"found": True, "category_id": 98345, "category_name": "น้ำปลา"}
    fake_entity_not_found = {"found": False, "category_id": None}

    print(search_from_entity(fake_entity_found)["status"])
    print(search_from_entity(fake_entity_not_found)["status"])