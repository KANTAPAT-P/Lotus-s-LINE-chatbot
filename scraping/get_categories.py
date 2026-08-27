"""
get_categories.py
--------------------------------
ดึง category tree ทั้งหมดจาก Lotus's Mobile BFF API แล้วแตก (flatten)
ออกมาเป็น list ของ "leaf category" (หมวดหมู่ระดับสุดท้ายที่มีสินค้าจริง
ไม่มีหมวดย่อยต่อไปอีก) เพื่อเอาไปใช้เป็น input ให้ scrap_all_product.py
วนลูป scrape ทีละหมวด

หมายเหตุสำคัญ:
- endpoint นี้ตอบ 304 Not Modified ได้ (มี Last-Modified header) แปลว่า
  โครงสร้างหมวดหมู่เปลี่ยนไม่บ่อย ไม่จำเป็นต้องเรียกซ้ำถี่ ๆ
- field "is_online" ในแต่ละ category สังเกตแล้วว่า "ไม่ได้บอกว่ามีสินค้า
  ขายอยู่จริงหรือเปล่า" (ทดสอบแล้วหมวดที่ is_online=0 ก็ยังมีสินค้า
  ขายจริงบนเว็บ) จึงไม่ใช้ field นี้กรองหมวดหมู่ที่จะ scrape
- leaf category = node ที่ children เป็น list ว่าง
"""

import json
import os
import requests

CATEGORY_URL = "https://api-o2o.lotuss.com/lotuss-mobile-bff/product/v4/categories"

# โครงสร้างโฟลเดอร์ตามภาพ: Lotus_line_chatbot/scraping/get_categories.py
# กับ Lotus_line_chatbot/data/categories/  -> เดินย้อนออกจาก scraping/ ไป data/categories/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "data", "categories")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "categories_flat.json")

DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "th",
    "channel": "web",
    "guest-id": "iizRY1xeR296vWPek1mNcQ",
    "key": "Vp9n5jPIPcNFHZMLsLBJ5iEMbFAcZpIK",
    "origin": "https://www.lotuss.com",
    "referer": "https://www.lotuss.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT_SECONDS = 10


def fetch_category_tree(seller_id: int = 3):
    """
    ดึง category tree ดิบทั้งหมดจาก API
    คืนค่าเป็น list ของ top-level category (dict) หรือ None ถ้า error
    """
    params = {"seller_id": seller_id, "is_in_menu": 1}
    try:
        response = requests.get(
            CATEGORY_URL,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("children", [])
    except requests.exceptions.RequestException as e:
        print(f"[get_categories] เกิด error ตอนดึง category tree: {e}")
        return None


def flatten_leaf_categories(categories, parent_names=None):
    """
    รับ list ของ category node (แบบ tree) แล้วแตกออกมาเป็น list แบนราบ
    ของเฉพาะ "leaf category" (children ว่าง) พร้อมเก็บชื่อหมวดหมู่แม่
    ไว้ด้วย (หมวดหมู่ใหญ่/หมวดหมู่ย่อย/ประเภทสินค้า) ตามที่วางแผนไว้

    คืนค่าเป็น list ของ dict:
        {
            "id": ...,
            "name": ...,
            "slug": ...,
            "path": ...,           # เช่น "76835/107486/107489/107495"
            "breadcrumb": [...]    # เช่น ["เนื้อสัตว์", "เนื้อวัว", "เนื้อวัว แช่แข็ง"]
        }
    """
    if parent_names is None:
        parent_names = []

    leaves = []
    for node in categories:
        current_names = parent_names + [node["name"]]
        children = node.get("children", [])

        if not children:
            leaves.append({
                "id": node["id"],
                "name": node["name"],
                "slug": node["slug"],
                "path": node["path"],
                "breadcrumb": current_names,
            })
        else:
            leaves.extend(flatten_leaf_categories(children, current_names))

    return leaves


if __name__ == "__main__":
    tree = fetch_category_tree()

    if tree is None:
        print("ดึง category tree ไม่สำเร็จ")
    else:
        leaves = flatten_leaf_categories(tree)
        print(f"จำนวนหมวดหมู่ใหญ่ (level 1): {len(tree)}")
        print(f"จำนวน leaf category ทั้งหมด: {len(leaves)}")

        # โชว์ตัวอย่าง 5 อันแรก ให้ดูว่า breadcrumb หน้าตาเป็นยังไง
        print("\nตัวอย่าง leaf category:")
        for leaf in leaves[:5]:
            print("-", " / ".join(leaf["breadcrumb"]), f"(id={leaf['id']})")

        # เก็บผลลัพธ์ไว้เป็น JSON ให้ scrap_all_product.py เอาไปใช้ต่อ
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(leaves, f, ensure_ascii=False, indent=2)
        print(f"\nบันทึกลง {OUTPUT_PATH} แล้ว")