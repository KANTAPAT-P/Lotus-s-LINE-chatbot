"""
find_live_product.py
--------------------------------
ค้นหาสินค้าผ่าน endpoint เดียวกับ scrap_current_product.py (search
endpoint ตัวเดียวกับที่ระบบเราใช้ค้นหาสดจริง) เพื่อดู JSON ในมุมมอง
ที่ตรงกับที่โค้ดเราจะเห็นจริง ๆ ต่างจากหน้ารายละเอียดสินค้า (product
detail page) ที่ field ไม่ตรงกัน

รันแล้วลบทิ้งได้เลย ไม่ใช่ไฟล์ถาวรของโปรเจกต์ ต้องรันจากโฟลเดอร์
scraping/ (หรือที่ไหนก็ได้ที่ import scrap_current_product ได้)

วิธีใช้: แก้ SEARCH_KEYWORD ด้านล่างเป็นคำที่อยากค้นหา แล้วรัน:
    python find_live_product.py
"""

import json
import sys
import os

# เผื่อรันจากที่อื่นที่ไม่ใช่ในโฟลเดอร์ scraping/ เอง
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "scraping"))
sys.path.append(SCRIPT_DIR)

from scrap_current_product import search_products

SEARCH_KEYWORD = "จินดา น้ำปลาหวาน"
NAME_FILTER_TERMS = ["จินดา", "น้ำปลาหวาน"]  # กรองเฉพาะชื่อที่มีครบทุกคำนี้ (กันได้สินค้าอื่นปนมา)


def main():
    raw = search_products(SEARCH_KEYWORD)
    if raw is None:
        print("เรียก API ไม่สำเร็จ (timeout หรือ network error)")
        return

    products = raw.get("data", {}).get("products", [])
    print(f"เจอสินค้าทั้งหมด {len(products)} ชิ้นจากคำค้น {SEARCH_KEYWORD!r}\n")

    matched = [p for p in products if all(term in p.get("name", "") for term in NAME_FILTER_TERMS)]

    if not matched:
        print(f"ไม่เจอสินค้าที่ชื่อมีครบทุกคำ {NAME_FILTER_TERMS} เลย "
              f"โชว์สินค้าชิ้นแรกที่เจอแทน (เผื่อดูโครงสร้างคร่าว ๆ):\n")
        matched = products[:1]

    for p in matched:
        print(f"=== {p.get('name')} ===")
        print(json.dumps(p, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()