"""
product_view_model.py
--------------------------------
แปลง "สินค้าดิบ" (จะมาจาก data/all_product/ หรือจาก
scrap_current_product.py fallback ก็ได้ทั้งคู่ — โครงสร้าง field ตรง
กันเพราะเป็น API เดียวกันของ Lotus's) ให้เป็น "view model" กลาง ที่
flex_builder.py เอาไปสร้าง Flex Message ต่อได้เลยโดยไม่ต้องรู้เรื่อง
promotions[] / ruleType / regex อะไรเลย

เหตุผลที่แยกชั้นนี้ออกมาต่างหาก (ไม่ยัดรวมไว้ใน flex_builder.py):
- ทดสอบ logic การเลือกว่าจะโชว์ badge แบบไหนได้แยกจากการสร้าง Flex
  JSON (ซึ่งเทสยากกว่าเพราะเป็น JSON ซ้อนลึกหลายชั้น)
- เรียก classify_promotion() กับสินค้า "ทุกชิ้นเสมอ" ไม่ใช่แค่ตอน
  intent=ask_promotion เพราะต่อให้ user ถามหาสินค้าเฉย ๆ แต่ถ้าชิ้นนั้น
  มีส่วนลดอยู่แล้วจริง ก็ควรโชว์ badge ให้เห็น ไม่ควรซ่อนไว้

Schema ของ view model ที่คืนออกไป:
    {
        "name": str,
        "image_url": str,
        "link": str หรือ None (None ถ้าไม่มี urlKey/sku ให้ประกอบลิงก์เลย),
        "price_current": number หรือ None,
        "price_original": number หรือ None (มีค่าเฉพาะตอนลด % เท่านั้น),
        "badge": {"type": str, "text": str, "color": str} หรือ None,
    }

--------------------------------
บันทึกการแก้บั๊ก: ลิงก์สินค้าใช้ field ผิด (sku แทน urlKey)
--------------------------------
ตอนแรกใช้ product["sku"] ประกอบลิงก์ เพราะตัวอย่างที่ทดสอบไว้ก่อนหน้า
(เช่น "โค้ก ซีโร่ ซีโร่") บังเอิญ sku กับ urlKey เป็นตัวเลขเดียวกันพอดี
("171472571" ทั้งคู่) เลยดูเหมือนใช้แทนกันได้ แต่เจอเคสจริงที่ urlKey
เป็น slug ข้อความ เช่น "scott-clean-care-3xl-3ply-roll-tissue-6pcs-
50422565" ไม่ใช่ตัวเลขล้วนเหมือน sku เลย ลิงก์ที่ประกอบจาก sku เลย
พาไปหน้าผิด ต้องใช้ product["urlKey"] เป็นหลักเสมอ (เก็บ sku ไว้เป็น
fallback เฉย ๆ เผื่อสินค้าบางชิ้นไม่มี urlKey จริง ๆ)
"""

from promotion_parser import classify_promotion

PLACEHOLDER_IMAGE = "https://via.placeholder.com/600x400.png?text=Lotus%27s"

# สีของ badge แต่ละประเภทโปรโมชั่น (ทำเป็นค่าคงที่ไว้ปรับง่าย ๆ)
BADGE_COLORS = {
    "percent_off": "#E4002B",              # แดง (Lotus's brand color)
    "buy_x_special_price": "#FF6B00",      # ส้ม
    "buy_x_get_x_free": "#7B2CBF",         # ม่วง
    "spend_threshold_discount": "#0072CE",  # ฟ้า (ซื้อครบ X ลดทันที X)
    "other": "#666666",                    # เทา (โปรแบบที่ไม่รู้จัก ยังโชว์ได้แต่ไม่เด่นเท่า)
}


def _build_badge(promo: dict):
    """
    รับผลลัพธ์จาก classify_promotion() คืนค่า badge dict หรือ None
    (None ถ้าสินค้าไม่มีโปรเลย -> แบบที่ 1 "สินค้าธรรมดา")
    """
    if not promo or not promo.get("has_promotion"):
        return None

    promo_type = promo["type"]
    details = promo.get("details")

    if promo_type == "percent_off":
        percent = details.get("percent_off") if details else None
        text = f"ลด {percent:.0f}%" if percent else "ลดราคา"

    elif promo_type == "buy_x_special_price":
        if details:
            text = f"ซื้อ {details['buy_qty']} ชิ้น {details['special_price']:.0f} บาท"
        else:
            text = promo.get("summary_text") or "ซื้อหลายชิ้นราคาพิเศษ"

    elif promo_type == "buy_x_get_x_free":
        if details:
            text = f"ซื้อ {details['buy_qty']} แถม {details['free_qty']}"
        else:
            text = promo.get("summary_text") or "ซื้อแถมฟรี"

    elif promo_type == "spend_threshold_discount":
        # summary_text ที่ classify_promotion() สร้างไว้แล้วกระชับพอ
        # จะเอามาใช้ตรง ๆ เลย (เช่น "ซื้อครบ 299.- ลด 10.- (สูงสุด 120.-)")
        text = promo.get("summary_text") or "ซื้อครบลดทันที"

    else:  # "other" -> ruleType ที่ไม่รู้จัก ยังโชว์ได้แต่ข้อความมาจาก summary_text ตรง ๆ
        text = promo.get("summary_text") or "มีโปรโมชั่น"

    return {
        "type": promo_type,
        "text": text,
        "color": BADGE_COLORS.get(promo_type, "#666666"),
    }


def build_view_model(product: dict) -> dict:
    """
    รับ dict สินค้า 1 ชิ้น (ดิบ ๆ ตามที่ scrape มา) คืนค่าเป็น view
    model ที่ flex_builder.py เอาไปใช้สร้างการ์ดได้เลย
    """
    if not product:
        return None

    name = product.get("name", "") or ""
    url_key = product.get("urlKey") or product.get("sku")  # urlKey คือตัวจริง, sku ไว้กันเหนียวเฉย ๆ
    image_url = product.get("thumbnail", {}).get("url") or PLACEHOLDER_IMAGE
    price_current = product.get("finalPricePerUOW")

    promo = classify_promotion(product)
    badge = _build_badge(promo)

    # ราคาก่อนลด โชว์เฉพาะตอนลด % เท่านั้น (แบบ 3-4 ราคาต่อชิ้นไม่ได้
    # ลดจริง ความคุ้มอยู่ที่เงื่อนไขซื้อ ไม่ใช่ราคาต่อชิ้น เลยไม่ขีดฆ่า)
    price_original = None
    if badge and badge["type"] == "percent_off" and promo.get("details"):
        price_original = promo["details"].get("regular_price")

    # ประกอบลิงก์จาก urlKey (ไม่ใช่ sku!) เจอเคสจริงที่ urlKey เป็น slug
    # ข้อความ เช่น "scott-clean-care-3xl-3ply-roll-tissue-6pcs-50422565"
    # ไม่ใช่ตัวเลขล้วนเหมือน sku เสมอไป บางชิ้นแค่บังเอิญ urlKey กับ sku
    # เป็นตัวเลขเดียวกันเท่านั้น ห้ามใช้ sku ประกอบลิงก์เด็ดขาด
    link = f"https://www.lotuss.com/th/product/{url_key}" if url_key else None

    return {
        "name": name,
        "image_url": image_url,
        "link": link,
        "price_current": price_current,
        "price_original": price_original,
        "badge": badge,
    }


def build_view_models(products: list) -> list:
    """แปลงสินค้าทั้ง list ทีเดียว (เอาไว้ใช้กับผลลัพธ์ top5_selector.py)"""
    return [build_view_model(p) for p in products if p]


# ----------------------------------
# ทดสอบเดี่ยว ๆ ด้วยตัวอย่างสินค้าจริงทั้ง 4 แบบ
# ----------------------------------
if __name__ == "__main__":
    # แบบ 1: สินค้าธรรมดา ไม่มีโปรเลย
    product_normal = {
        "name": "น้ำดื่มสิงห์ 600 มล.", "sku": "12345678", "urlKey": "12345678",
        "thumbnail": {"url": "https://example.com/water.jpg"},
        "finalPricePerUOW": 7, "regularPricePerUOW": 7,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
    }

    # แบบ 2: ลด % (เทสโต)
    product_percent_off = {
        "name": "เทสโต แผ่นหยัก กลิ่นหมึกย่างทะเลเดือด 40 กรัม แพ็ค 6", "sku": "75723319", "urlKey": "75723319",
        "thumbnail": {"url": "https://o2o-static.lotuss.com/products/86593/75723319.jpg"},
        "finalPricePerUOW": 79, "regularPricePerUOW": 99,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 20, "percentOff": 20.2}}},
        "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
    }

    # แบบ 3: ซื้อ X ราคาพิเศษ (โค้ก)
    product_buy_special = {
        "name": "โค้ก ซีโร่ ซีโร่ 325 มล. แพ็ค 6", "sku": "171472571", "urlKey": "171472571",
        "thumbnail": {"url": "https://o2o-static.lotuss.com/products/91129/171472571.jpg"},
        "finalPricePerUOW": 78, "regularPricePerUOW": 78,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"offerText": "Promotion Badge", "ruleType": "bxf"}],
        "autoBadge": {"imagePromotion": {"items": [
            {"items": [{"description": "ซื้อ 2 ชิ้น 153.0 บาท", "ruleType": "bxf"}], "name": "promotionRpm"}
        ]}},
    }

    # แบบ 4: ซื้อ X แถม X (เลย์แมกซ์)
    product_buy_free = {
        "name": "เลย์แมกซ์ กลิ่นปูผัดผงกะหรี่ ปูอัดกรอบ 60 กรัม", "sku": "75730961", "urlKey": "75730961",
        "thumbnail": {"url": "https://o2o-static.lotuss.com/products/86593/75730961.jpg"},
        "finalPricePerUOW": 31, "regularPricePerUOW": 31,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"offerText": "Promotion Badge", "ruleType": "bxgx"}],
        "autoBadge": {"imagePromotion": {"items": [
            {"items": [{"description": "ซื้อ 2 แถม 1", "ruleType": "bxgx"}], "name": "promotionRpm"}
        ]}},
    }

    # เคสที่เจอบั๊กจริง: sku กับ urlKey เป็นคนละค่ากัน (urlKey เป็น slug
    # ไม่ใช่ตัวเลข) ต้องใช้ urlKey ประกอบลิงก์ ไม่ใช่ sku
    product_slug_urlkey = {
        "name": "สก็อตต์ คลีนแคร์ กระดาษชำระ 3 ชั้น 3XL แพ็ค 6",
        "sku": "50422565",  # sku เป็นตัวเลข
        "urlKey": "scott-clean-care-3xl-3ply-roll-tissue-6pcs-50422565",  # urlKey เป็น slug คนละแบบ
        "thumbnail": {"url": "https://example.com/tissue.jpg"},
        "finalPricePerUOW": 89, "regularPricePerUOW": 89,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
    }

    for label, product in [
        ("แบบ 1: ธรรมดา", product_normal),
        ("แบบ 2: ลด %", product_percent_off),
        ("แบบ 3: ซื้อ X ราคาพิเศษ", product_buy_special),
        ("แบบ 4: ซื้อ X แถม X", product_buy_free),
        ("เคสบั๊ก: urlKey เป็น slug ต่างจาก sku", product_slug_urlkey),
    ]:
        print(f"=== {label} ===")
        vm = build_view_model(product)
        for k, v in vm.items():
            print(f"  {k}: {v}")
        print()