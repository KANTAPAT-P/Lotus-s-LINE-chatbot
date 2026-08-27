"""
find_product.py
--------------------------------
สคริปต์ชั่วคราวสำหรับหา JSON ดิบของสินค้าที่ต้องการดู จาก data/all_product/
รันแล้วลบทิ้งได้เลย ไม่ใช่ไฟล์ถาวรของโปรเจกต์

วิธีใช้: แก้ SEARCH_TERMS ด้านล่างเป็นคำที่อยากค้นหา แล้วรัน:
    python find_product.py
"""

import json
import glob

# แก้ตรงนี้เป็นคำที่อยากค้นหา (ต้องมีครบทุกคำในชื่อสินค้าถึงจะ match)
SEARCH_TERMS = ["จินดา", "น้ำปลาหวาน","สูตรเผ็ด"]

found = False
for filepath in glob.glob("data/all_product/*.json"):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    for p in data.get("products", []):
        name = p.get("name", "")
        if all(term in name for term in SEARCH_TERMS):
            print(f"เจอในไฟล์: {filepath}")
            print(json.dumps(p, ensure_ascii=False, indent=2))
            found = True
            break

    if found:
        break

if not found:
    print(f"ไม่เจอสินค้าที่มีคำว่า {SEARCH_TERMS} ในชื่อเลย ลองปรับ SEARCH_TERMS ดูใหม่")