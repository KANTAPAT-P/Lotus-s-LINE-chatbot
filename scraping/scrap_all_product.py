"""
scrap_all_product.py
--------------------------------
Scrape สินค้าทั้งหมดของ Lotus's แบบ batch/offline โดยวนลูปทีละ
"leaf category" (จาก data/categories/categories_flat.json ที่
get_categories.py สร้างไว้) แล้วเก็บผลลัพธ์เป็นไฟล์ JSON แยกตาม
หมวดหมู่ไว้ที่ data/all_product/

จุดออกแบบสำคัญ (ตามที่คุยกันไว้ก่อนหน้า):
1. รันแยกจาก webhook_server.py โดยสิ้นเชิง (เป็น batch job ไม่ใช่
   เรียกสดตอน user ถาม) จะได้ไม่ชนเรื่อง timeout 30 วิของ LINE
2. Resumable: ก่อน scrape แต่ละหมวด เช็คว่ามีไฟล์ผลลัพธ์อยู่แล้วหรือยัง
   ถ้ามีแล้ว "ข้าม" ไปเลย ไม่ scrape ซ้ำ -> รันต่อจากจุดที่ค้างได้
   ถ้า process ถูกตัดกลางทาง (เน็ตหลุด/ปิดเครื่อง) แค่รันสคริปต์ใหม่
   อีกรอบ มันจะ scrape ต่อจากหมวดที่ยังไม่มีไฟล์เท่านั้น
3. เขียนไฟล์ทันทีที่ scrape หมวดนั้นเสร็จ (ไม่รอสะสมในหน่วยความจำ
   จนจบทั้งหมดค่อยเขียน) เพื่อไม่ให้เสียงานที่ทำไปแล้วถ้าล้มกลางทาง
4. มี REQUEST_DELAY_SECONDS หน่วงเวลาระหว่างแต่ละ request กันโดน
   rate limit / บล็อก ตามเกณฑ์ "เว้นระยะการดึงข้อมูลอย่างเหมาะสม"
"""

import json
import os
import time
import requests

PRODUCTS_URL = "https://api-o2o.lotuss.com/lotuss-mobile-bff/product/v4/products"

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
PAGE_SIZE = 50            # ต่อ request ขอทีละกี่ชิ้น (ยิ่งเยอะ ยิ่งเรียกน้อยครั้ง)
MAX_PAGES_PER_CATEGORY = 50   # กันลูปไม่รู้จบ เผื่อ API แปลก ๆ
REQUEST_DELAY_SECONDS = 0.8   # หน่วงเวลาระหว่างแต่ละ request (เป็น batch job ไม่รีบ)
CATEGORY_DELAY_SECONDS = 1.0  # หน่วงเวลาระหว่างแต่ละหมวดหมู่เพิ่มอีกนิด

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_PATH = os.path.join(SCRIPT_DIR, "..", "data", "categories", "categories_flat.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "data", "all_product")


def load_leaf_categories():
    """โหลด leaf category list ที่ get_categories.py เตรียมไว้"""
    if not os.path.exists(CATEGORIES_PATH):
        print(f"ไม่พบไฟล์ {CATEGORIES_PATH} — รัน get_categories.py ก่อนนะ")
        return []

    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_products_page(category_id: int, page: int, seller_id: int = 3):
    """
    ยิง GET ไปที่ products endpoint สำหรับหมวดหมู่ + หน้าที่ระบุ
    คืนค่าเป็น dict ของ JSON ดิบ หรือ None ถ้า error
    """
    params = {
        "category_id": category_id,
        "page": page,
        "limit": PAGE_SIZE,
        "seller_id": seller_id,
    }
    try:
        response = requests.get(
            PRODUCTS_URL,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"    [error] category_id={category_id} page={page}: {e}")
        return None


def fetch_all_products_in_category(category_id: int):
    """
    ไล่ scrape ทุกหน้าของหมวดหมู่หนึ่ง ๆ จนกว่าจะหมด
    คืนค่าเป็น list ของสินค้าทั้งหมดในหมวดนั้น (อาจว่างถ้าไม่มีสินค้า)
    """
    all_products = []

    for page in range(1, MAX_PAGES_PER_CATEGORY + 1):
        raw = fetch_products_page(category_id, page)
        time.sleep(REQUEST_DELAY_SECONDS)  # หน่วงเวลาทุกครั้งที่ยิง request

        if raw is None:
            # ยิง error กลางคัน -> หยุดหมวดนี้ไว้ก่อน (ไม่ลบของที่ได้มาแล้ว)
            break

        products = raw.get("data", {}).get("products", [])
        if not products:
            # หน้านี้ไม่มีสินค้าแล้ว แปลว่าหมดแล้ว
            break

        all_products.extend(products)

        # ถ้าจำนวนสินค้าที่ได้น้อยกว่าที่ขอ (limit) แปลว่าเป็นหน้าสุดท้าย
        if len(products) < PAGE_SIZE:
            break

    return all_products


def safe_filename(leaf: dict) -> str:
    """
    ตั้งชื่อไฟล์ผลลัพธ์ต่อหมวดหมู่ โดยใช้ id นำหน้าเสมอ (กันชื่อชนกัน
    เพราะบางหมวดหมู่ใช้ชื่อ/slug ซ้ำกันได้ เช่น "food" หลายที่)
    """
    return f"{leaf['id']}_{leaf['slug']}.json"


def run():
    leaves = load_leaf_categories()
    if not leaves:
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total = len(leaves)
    print(f"ทั้งหมด {total} leaf category")

    for i, leaf in enumerate(leaves, start=1):
        out_path = os.path.join(OUTPUT_DIR, safe_filename(leaf))
        breadcrumb_text = " / ".join(leaf["breadcrumb"])

        # ---------- Resume: ข้ามถ้ามีไฟล์อยู่แล้ว ----------
        if os.path.exists(out_path):
            print(f"[{i}/{total}] ข้าม (มีไฟล์แล้ว): {breadcrumb_text}")
            continue

        print(f"[{i}/{total}] กำลัง scrape: {breadcrumb_text} (id={leaf['id']})")

        products = fetch_all_products_in_category(leaf["id"])

        result = {
            "category_id": leaf["id"],
            "category_name": leaf["name"],
            "breadcrumb": leaf["breadcrumb"],
            "path": leaf["path"],
            "product_count": len(products),
            "products": products,
        }

        # ---------- เขียนไฟล์ทันที ไม่รอสะสม ----------
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"    -> เจอ {len(products)} รายการ บันทึกที่ {out_path}")

        time.sleep(CATEGORY_DELAY_SECONDS)

    print("\nscrape ครบทุกหมวดหมู่แล้ว (หรือรันต่อจากจุดที่ค้างจบแล้ว)")


if __name__ == "__main__":
    run()