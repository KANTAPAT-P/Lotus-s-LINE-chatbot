"""
scrap_current_product.py
--------------------------------
ดึงผลการค้นหาสินค้าแบบ real-time จาก Lotus's Mobile BFF API
(เจอ endpoint นี้จากการดู Network tab ตอนพิมพ์ค้นหาในหน้าเว็บ lotuss.com)

หมายเหตุ:
- endpoint นี้ไม่ได้เช็ค auth เข้มงวด (Guest-Id / Key / sessionId
  ใส่ค่าอะไรไปก็ยังได้ผลลัพธ์กลับมา) แต่ยังคงใส่ header ให้ครบ
  ตามที่เว็บจริงส่งมา เผื่ออนาคตมีการเช็คเพิ่ม
- ตอนนี้แค่ยิง request แล้วคืน JSON ดิบกลับไปก่อน ยังไม่ parse
  field อะไรทั้งนั้น (ไว้ปรับตามหน้างานทีหลัง)
"""

import requests

SEARCH_URL = "https://api-o2o.lotuss.com/lotuss-mobile-bff/product/v6/search"

# ค่าพวกนี้ทดสอบแล้วว่าใส่มั่วก็ยังใช้ได้ (ดู README/บันทึกการทดสอบ)
# แต่คงรูปแบบไว้ให้เหมือน request จริงจากเบราว์เซอร์
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "th",
    "channel": "web",
    "content-type": "application/json",
    "guest-id": "iizRY1xeR296vWPek1mNcQ",
    "key": "Vp9n5jPIPcNFHZMLsLBJ5iEMbFAcZpIK",
    "origin": "https://www.lotuss.com",
    "referer": "https://www.lotuss.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ตั้ง timeout ให้ต่ำกว่ามาก ๆ เมื่อเทียบกับเพดาน 30 วิของ LINE reply token
# (เผื่อเวลาให้ขั้นตอนอื่น ๆ เช่น intent detection, build flex message ด้วย)
REQUEST_TIMEOUT_SECONDS = 8


def search_products(keyword: str, limit: int = 15, page: int = 1, seller_id: int = 3):
    """
    ยิง POST ไปที่ Lotus search API ด้วยคำค้นหา (keyword)
    คืนค่าเป็น dict ของ JSON ดิบที่ได้กลับมา (ยังไม่ parse)
    ถ้า error หรือ timeout จะคืน None แทน (กันไม่ให้ webhook ค้าง)
    """
    params = {
        "sort": "relevance:DESC",
        "limit": limit,
        "page": page,
        "seller_id": seller_id,
    }
    payload = {
        "keyword": keyword,
        "sessionId": "test-session-0001",  # ใส่ค่าอะไรก็ได้ ตามที่ทดสอบไว้
    }

    try:
        response = requests.post(
            SEARCH_URL,
            params=params,
            json=payload,  # ใช้ json= ให้ requests จัดการ UTF-8 encoding ให้เอง
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        print(f"[scrap_current_product] Timeout ตอนค้นหา keyword='{keyword}'")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[scrap_current_product] เกิด error: {e}")
        return None


def search_products_status(keyword: str, limit: int = 15, page: int = 1, seller_id: int = 3):
    """
    เหมือน search_products() แต่ห่อผลลัพธ์ให้บอก "สถานะ" ชัดเจน
    เพื่อให้ webhook_server.py เอาไปเช็คแล้วตัดสินใจตอบ user ได้ง่าย
    (แยก error ของระบบ ออกจาก "หาไม่เจอสินค้าจริง ๆ" เพราะทั้งคู่
    ฝั่ง API ตอบ code 200 เหมือนกัน ต้องเช็คจาก products ว่าง/ไม่ว่างเอง)

    คืนค่าเป็น dict เสมอ รูปแบบ:
        {
            "status": "found" | "not_found" | "error",
            "products": [...],   # list สินค้าดิบจาก API (ว่างถ้า not_found/error)
            "raw": {...} | None, # JSON เต็ม ๆ เผื่ออยากดู field อื่นเพิ่ม (เช่น filters)
        }

    ความหมายของแต่ละ status:
    - "found"     : เจอสินค้าอย่างน้อย 1 รายการ
    - "not_found" : เรียก API สำเร็จ (code 200) แต่ products เป็น list ว่าง
    - "error"     : เรียก API ไม่สำเร็จ (timeout / network error / status ไม่ใช่ 2xx)
    """
    raw = search_products(keyword, limit=limit, page=page, seller_id=seller_id)

    if raw is None:
        return {"status": "error", "products": [], "raw": None}

    products = raw.get("data", {}).get("products", [])

    if not products:
        return {"status": "not_found", "products": [], "raw": raw}

    return {"status": "found", "products": products, "raw": raw}


# ----------------------------------
# ลองรันเดี่ยว ๆ เพื่อดูผลลัพธ์
# ----------------------------------
if __name__ == "__main__":
    for keyword in ["cheetos", "DFBAKJH"]:  # คำที่เจอสินค้า + คำที่ไม่เจอ (ทดสอบทั้ง 2 เคส)
        print(f"\n=== ค้นหา: '{keyword}' ===")
        result = search_products_status(keyword)

        print(f"status: {result['status']}")

        if result["status"] == "error":
            print("ดึงข้อมูลไม่สำเร็จ (timeout หรือ network error)")
        elif result["status"] == "not_found":
            print("เรียก API สำเร็จ แต่ไม่พบสินค้า")
        else:
            products = result["products"]
            print(f"จำนวนสินค้าที่เจอ: {len(products)}")
            for p in products[:5]:
                print("-", p.get("name"))