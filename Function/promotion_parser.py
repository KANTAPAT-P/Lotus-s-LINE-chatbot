"""
promotion_parser.py
--------------------------------
จำแนกประเภทโปรโมชั่นของสินค้า 1 ชิ้น จาก field ที่ scrape มาเก็บไว้แล้ว
(ไม่ต้อง scrape หน้าโปรโมชั่นแยกต่างหาก เพราะ field พวกนี้ติดมากับ
ข้อมูลสินค้าทุกชิ้นอยู่แล้วใน data/all_product/ หรือผลลัพธ์จาก
scrap_current_product.py)

--------------------------------
บันทึกการออกแบบ (สำคัญ อ่านก่อนแก้โค้ดส่วนนี้)
--------------------------------
เจอ 4 รูปแบบโปรโมชั่นจากตัวอย่างข้อมูลจริง แต่ "ตำแหน่งที่เก็บ" ไม่
เหมือนกันเลย ต้องรู้ไว้ก่อนแก้:

1. ลดราคา % ธรรมดา (เช่น "เทสโต แผ่นหยัก" ลด 20.2%)
   -> field "promotions" ว่างเปล่า! ต้องเช็คจาก
      priceRange.minimumPrice.discount.percentOff แทน

2. ซื้อ X ชิ้น ราคาพิเศษ X บาท (เช่น "โค้ก ซีโร่ ซีโร่" ซื้อ 2 ชิ้น 153 บาท)
   -> promotions[0].ruleType == "bxf" (buy-x-for)
   -> รายละเอียดตัวเลขจริง ๆ ไม่ได้อยู่ใน promotions[] แต่ซ้อนอยู่ใน
      autoBadge.imagePromotion.items[].items[].description
      (ข้อความอิสระ เช่น "ซื้อ 2 ชิ้น 153.0 บาท") ต้อง parse ด้วย regex

3. ซื้อ X แถม X (เช่น "เลย์แมกซ์" ซื้อ 2 แถม 1)
   -> promotions[0].ruleType == "bxgx" (buy-x-get-x)
   -> รายละเอียดอยู่ที่เดียวกับข้อ 2 (autoBadge.imagePromotion...) เช่น
      "ซื้อ 2 แถม 1"

4. ซื้อครบ X บาท ลดทันที X บาท แบบหลายระดับ (เช่น "จินดา น้ำปลาหวาน"
   ซื้อครบ 299 ลด 10 / ซื้อครบ 499 ลด 20 / ... ไล่ขึ้นไปเรื่อย ๆ)
   -> promotions[0].ruleType == "bxtpgd" (ย่อมาจากประมาณ "buy x total
      price get discount")
   -> *** ต่างจาก bxf/bxgx ตรงที่ข้อความเต็มอยู่ที่ promotions[0]
      ["offerText"] โดยตรงเลย ไม่ต้องขุดเข้า autoBadge เหมือน 2 แบบ
      ก่อน *** (autoBadge ของ bxtpgd อยู่ใต้ "percentPriceOff" ไม่ใช่
      "imagePromotion" แถม field "description" ว่างเปล่า มีแต่
      "offerText" ที่มีข้อมูลจริง ตำแหน่งไม่ตรงกับ 2 แบบก่อนเลย)
   -> รูปแบบข้อความเป็นหลายระดับต่อกันด้วย "<br>" เช่น
      "ซื้อครบ 299.- ลดทันที 10.-<br>ซื้อครบ 499.- ลดทันที 20.-<br>..."
      parse ด้วย regex ดึงเป็น list ของคู่ (ยอดซื้อ, ส่วนลด) ทั้งหมด
      แล้วโชว์ใน badge แค่ "ระดับแรกสุด + ส่วนลดสูงสุด" (กระชับกว่า
      เอาข้อความดิบทั้งหมดมาแปะตรง ๆ ซึ่งยาวเป็นพรืดและมี "<br>" ดิบ
      ติดมาด้วย ตามที่เคยเจอบั๊กจริงตอนทดสอบ)

ruleType ที่ไม่รู้จักเลย (ไม่ใช่ทั้ง 3 แบบข้างบน) ให้จัดเป็น "other"
ไม่ error ทิ้ง เผื่อ Lotus's มีโปรแบบอื่นที่ยังไม่เจอในตัวอย่างที่
ทดสอบมา (แต่จำกัดความยาว + ตัด "<br>" ออกด้วย กันบั๊กแบบเดียวกับที่
เจอตอน bxtpgd ก่อนที่จะรู้จักมันจริง ๆ)
"""

import re

# ----------------------------------
# regex สำหรับดึงตัวเลขจากข้อความโปรโมชั่นอิสระ (description/offerText)
# ----------------------------------
# ตัวอย่างที่ต้อง match: "ซื้อ 2 ชิ้น 153.0 บาท"
_RE_BUY_SPECIAL_PRICE = re.compile(r"ซื้อ\s*(\d+)\s*ชิ้น\s*([\d.]+)\s*บาท")
# ตัวอย่างที่ต้อง match: "ซื้อ 2 แถม 1"
_RE_BUY_GET_FREE = re.compile(r"ซื้อ\s*(\d+)\s*แถม\s*(\d+)")
# ตัวอย่างที่ต้อง match (หลายจุดในข้อความเดียว): "ซื้อครบ 299.- ลดทันที 10.-"
# ตัวเลขอาจมี comma คั่นหลักพัน (เช่น "1,499") ต้องรับด้วย
_RE_SPEND_THRESHOLD_DISCOUNT = re.compile(r"ซื้อครบ\s*([\d,]+)\.-\s*ลดทันที\s*([\d,]+)\.-")

# จำกัดความยาว summary_text สูงสุดสำหรับเคสที่ parse อะไรไม่ได้เลย
# (fallback เป็นข้อความดิบ) กันบั๊กแบบที่เคยเจอตอน bxtpgd ก่อนรู้จักมัน
# จริง ๆ (เอาข้อความดิบยาวเป็นพรืดพร้อม "<br>" ดิบมาแปะใน badge ตรง ๆ)
_MAX_FALLBACK_TEXT_LENGTH = 60


def _clean_raw_offer_text(text: str) -> str:
    """
    ทำความสะอาดข้อความโปรโมชั่นดิบที่ parse แบบเจาะจงไม่ได้ (fallback
    สุดท้าย): แทน "<br>" ด้วยช่องว่าง แล้วตัดให้สั้นลงถ้ายาวเกินไป
    ป้องกัน badge ยาวเป็นพรืดพร้อม HTML tag ดิบติดไปด้วย (บั๊กที่เคย
    เจอจริงตอน ruleType="bxtpgd" ก่อนที่จะรู้จักและ parse มันได้)
    """
    if not text:
        return text
    cleaned = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE).strip()
    if len(cleaned) > _MAX_FALLBACK_TEXT_LENGTH:
        cleaned = cleaned[:_MAX_FALLBACK_TEXT_LENGTH - 3] + "..."
    return cleaned


def _parse_spend_threshold_tiers(offer_text: str):
    """
    parse ข้อความแบบ "ซื้อครบ 299.- ลดทันที 10.-<br>ซื้อครบ 499.- ลด
    ทันที 20.-<br>..." เป็น list ของ (ยอดซื้อขั้นต่ำ, ส่วนลด) เรียง
    จากน้อยไปมากตามลำดับที่เจอในข้อความ (เชื่อว่า Lotus's เรียงจาก
    ระดับต่ำสุดไปสูงสุดอยู่แล้วตามที่เห็นในตัวอย่างจริงทุกเคส)
    คืน list ว่างถ้า parse ไม่ได้เลยสักคู่ (รูปแบบข้อความเปลี่ยนไป)
    """
    matches = _RE_SPEND_THRESHOLD_DISCOUNT.findall(offer_text)
    tiers = []
    for spend_str, discount_str in matches:
        try:
            spend = float(spend_str.replace(",", ""))
            discount = float(discount_str.replace(",", ""))
            tiers.append((spend, discount))
        except ValueError:
            continue
    return tiers


def _extract_promotion_description(product: dict) -> str:
    """
    ขุดหาข้อความอธิบายโปรโมชั่นแบบอิสระ (เช่น "ซื้อ 2 แถม 1") ที่ซ่อนอยู่
    ใน autoBadge.imagePromotion.items[].items[].description
    คืนข้อความแรกที่เจอ หรือ "" ถ้าไม่มีเลย (กัน error ถ้าโครงสร้าง
    ไม่ครบตามที่คาด เพราะสินค้าบางชิ้นอาจไม่มี field พวกนี้เลย)
    """
    try:
        promo_items = product.get("autoBadge", {}).get("imagePromotion", {}).get("items", [])
        for group in promo_items:
            for item in group.get("items", []):
                desc = item.get("description")
                if desc:
                    return desc
    except AttributeError:
        # เผื่อโครงสร้างข้อมูลผิดรูปแบบไปเลย (เช่น items ไม่ใช่ list)
        pass
    return ""


def classify_promotion(product: dict) -> dict:
    """
    รับ dict สินค้า 1 ชิ้น (ตามโครงสร้างที่ scrape มาจาก Lotus's)
    คืนค่าเป็น dict สรุปโปรโมชั่น:
        {
            "has_promotion": True/False,
            "type": "percent_off" | "buy_x_special_price" |
                    "buy_x_get_x_free" | "other" | "none",
            "summary_text": ข้อความอธิบายสั้น ๆ พร้อมเอาไปโชว์ user เลย,
            "details": {...} หรือ None (ตัวเลขที่ parse ได้ ถ้ามี),
        }
    """
    empty_result = {"has_promotion": False, "type": "none", "summary_text": "", "details": None}

    if not product:
        return empty_result

    # ---------- ขั้นที่ 1: เช็คส่วนลด % ก่อน (ไม่ได้อยู่ใน promotions[]) ----------
    discount = (
        product.get("priceRange", {})
        .get("minimumPrice", {})
        .get("discount", {})
    )
    percent_off = discount.get("percentOff", 0)

    if percent_off and percent_off > 0:
        regular_price = product.get("regularPricePerUOW")
        final_price = product.get("finalPricePerUOW")
        summary = f"ลด {percent_off:.0f}% (จาก {regular_price} บาท เหลือ {final_price} บาท)"
        return {
            "has_promotion": True,
            "type": "percent_off",
            "summary_text": summary,
            "details": {
                "percent_off": percent_off,
                "amount_off": discount.get("amountOff"),
                "regular_price": regular_price,
                "final_price": final_price,
            },
        }

    # ---------- ขั้นที่ 2: เช็ค promotions[] (ซื้อ X ราคาพิเศษ / ซื้อ X แถม X) ----------
    promotions = product.get("promotions", [])
    if not promotions:
        return empty_result

    rule_type = promotions[0].get("ruleType")
    description = _extract_promotion_description(product)

    if rule_type == "bxf":
        match = _RE_BUY_SPECIAL_PRICE.search(description) if description else None
        details = None
        if match:
            details = {
                "buy_qty": int(match.group(1)),
                "special_price": float(match.group(2)),
            }
        return {
            "has_promotion": True,
            "type": "buy_x_special_price",
            "summary_text": description or "มีโปรโมชั่นซื้อหลายชิ้นราคาพิเศษ",
            "details": details,
        }

    if rule_type == "bxgx":
        match = _RE_BUY_GET_FREE.search(description) if description else None
        details = None
        if match:
            details = {
                "buy_qty": int(match.group(1)),
                "free_qty": int(match.group(2)),
            }
        return {
            "has_promotion": True,
            "type": "buy_x_get_x_free",
            "summary_text": description or "มีโปรโมชั่นซื้อแถมฟรี",
            "details": details,
        }

    if rule_type == "bxtpgd":
        # *** ต่างจาก bxf/bxgx ตรงที่ข้อความเต็มอยู่ที่ offerText ของ
        # promotions[0] โดยตรง ไม่ต้องขุดเข้า autoBadge เลย (ดู docstring
        # บนสุดของไฟล์ อธิบายไว้ว่าทำไมตำแหน่งถึงไม่เหมือน 2 แบบก่อน) ***
        offer_text = promotions[0].get("offerText", "")
        tiers = _parse_spend_threshold_tiers(offer_text)

        if tiers:
            min_spend, min_discount = tiers[0]
            max_discount = max(discount for _, discount in tiers)
            summary = f"ซื้อครบ {min_spend:,.0f}.- ลด {min_discount:,.0f}.- (สูงสุด {max_discount:,.0f}.-)"
            return {
                "has_promotion": True,
                "type": "spend_threshold_discount",
                "summary_text": summary,
                "details": {"tiers": tiers},
            }

        # parse ไม่ได้เลยสักคู่ (รูปแบบข้อความเปลี่ยนไปจากที่คาด) ->
        # fallback เป็นข้อความดิบที่ทำความสะอาดแล้ว (ไม่ใช่ error)
        print(f"[promotion_parser] ruleType='bxtpgd' แต่ parse offerText ไม่ได้ตามรูปแบบที่คาด: "
              f"{offer_text!r} -> fallback เป็นข้อความดิบที่ทำความสะอาดแล้ว")
        return {
            "has_promotion": True,
            "type": "other",
            "summary_text": _clean_raw_offer_text(offer_text) or "มีโปรโมชั่นซื้อครบลดทันที",
            "details": {"raw_rule_type": rule_type},
        }

    # ---------- ruleType ที่ไม่รู้จักเลย -> จัดเป็น "other" ไม่ error ทิ้ง ----------
    print(f"[promotion_parser] เจอ ruleType ที่ไม่รู้จัก: {rule_type!r} "
          f"(สินค้า: {product.get('name')!r}) -> จัดเป็น 'other'")
    raw_text = description or promotions[0].get("offerText", "มีโปรโมชั่น")
    return {
        "has_promotion": True,
        "type": "other",
        "summary_text": _clean_raw_offer_text(raw_text),
        "details": {"raw_rule_type": rule_type},
    }


def filter_products_with_promotion(products: list) -> list:
    """
    รับ list สินค้า คืนค่าเฉพาะสินค้าที่มีโปรโมชั่นจริง (has_promotion=True)
    พร้อมแนบผลการจำแนกไว้ใน key "promotion_info" ของแต่ละชิ้น
    เอาไว้ใช้ตอน intent = ask_promotion (กรองเฉพาะของที่มีโปรจริง ๆ
    ก่อนส่งต่อไป top5_selector.py)
    """
    result = []
    for product in products:
        info = classify_promotion(product)
        if info["has_promotion"]:
            enriched = dict(product)
            enriched["promotion_info"] = info
            result.append(enriched)
    return result


# ----------------------------------
# ทดสอบเดี่ยว ๆ ด้วยตัวอย่างข้อมูลจริงทั้ง 3 แบบ
# ----------------------------------
if __name__ == "__main__":
    # แบบที่ 1: ลด % (promotions ว่างเปล่า แต่มี discount)
    product_percent_off = {
        "name": "เทสโต แผ่นหยัก กลิ่นหมึกย่างทะเลเดือด 40 กรัม แพ็ค 6",
        "regularPricePerUOW": 99,
        "finalPricePerUOW": 79,
        "priceRange": {
            "minimumPrice": {
                "discount": {"amountOff": 20, "percentOff": 20.2, "displayNumber": 20, "displayText": ""}
            }
        },
        "promotions": [],
        "autoBadge": {"imagePromotion": {"items": []}},
    }

    # แบบที่ 2: ซื้อ X ราคาพิเศษ X บาท
    product_buy_special_price = {
        "name": "โค้ก ซีโร่ ซีโร่ 325 มล. แพ็ค 6",
        "regularPricePerUOW": 78,
        "finalPricePerUOW": 78,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"offerText": "Promotion Badge", "image": "", "ruleType": "bxf"}],
        "autoBadge": {
            "imagePromotion": {
                "items": [
                    {"items": [{"description": "ซื้อ 2 ชิ้น 153.0 บาท", "ruleType": "bxf"}], "name": "promotionRpm"}
                ]
            }
        },
    }

    # แบบที่ 3: ซื้อ X แถม X
    product_buy_get_free = {
        "name": "เลย์แมกซ์ กลิ่นปูผัดผงกะหรี่ ปูอัดกรอบ 60 กรัม",
        "regularPricePerUOW": 31,
        "finalPricePerUOW": 31,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"offerText": "Promotion Badge", "image": "", "ruleType": "bxgx"}],
        "autoBadge": {
            "imagePromotion": {
                "items": [
                    {"items": [{"description": "ซื้อ 2 แถม 1", "ruleType": "bxgx"}], "name": "promotionRpm"}
                ]
            }
        },
    }

    # เคสไม่มีโปรเลย
    product_no_promo = {
        "name": "สินค้าธรรมดาไม่มีโปร",
        "regularPricePerUOW": 50,
        "finalPricePerUOW": 50,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [],
        "autoBadge": {"imagePromotion": {"items": []}},
    }

    # เคส ruleType แปลก ๆ ที่ไม่รู้จักจริง ๆ (ไม่ใช่ 3 แบบที่รู้จักแล้ว)
    product_unknown_rule = {
        "name": "สินค้าโปรแปลก ๆ",
        "regularPricePerUOW": 100,
        "finalPricePerUOW": 100,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"offerText": "โปรพิเศษ", "ruleType": "some_new_rule_type"}],
        "autoBadge": {"imagePromotion": {"items": []}},
    }

    # แบบที่ 4: ซื้อครบ X ลดทันที X (จินดา น้ำปลาหวาน - ข้อมูลจริงที่เจอบั๊ก)
    product_spend_threshold = {
        "name": "จินดา น้ำปลาหวาน สูตรเผ็ด",
        "regularPricePerUOW": 49,
        "finalPricePerUOW": 49,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [
            {
                "ruleType": "bxtpgd",
                "promotionId": 204672,
                "offerText": (
                    "ซื้อครบ 299.- ลดทันที 10.-<br>ซื้อครบ 499.- ลดทันที 20.-<br>"
                    "ซื้อครบ 899.- ลดทันที 40.-<br>ซื้อครบ 1,499.- ลดทันที 80.-<br>"
                    "ซื้อครบ 1,899.- ลดทันที 120.-<br>สินค้า อาหารสด ที่ร่วมรายการ"
                ),
            },
        ],
        "autoBadge": {
            "imagePromotion": {"items": []},  # ว่างเปล่า! ต่างจาก bxf/bxgx
            "percentPriceOff": {
                "items": [
                    {"items": [{"description": "", "offerText": "...", "ruleType": "bxtpgd"}], "name": "instantDiscount"}
                ]
            },
        },
    }

    # เคส bxtpgd ที่ parse ไม่ได้ (จำลองว่า Lotus's เปลี่ยนรูปแบบข้อความ)
    product_spend_threshold_unparseable = {
        "name": "สินค้าทดสอบ bxtpgd รูปแบบแปลก",
        "regularPricePerUOW": 100,
        "finalPricePerUOW": 100,
        "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
        "promotions": [{"ruleType": "bxtpgd", "offerText": "โปรโมชั่นพิเศษ ซื้อเยอะลดเยอะ ติดต่อพนักงาน"}],
        "autoBadge": {"imagePromotion": {"items": []}},
    }

    test_products = [
        ("ลด % (เทสโต)", product_percent_off),
        ("ซื้อ X ราคาพิเศษ (โค้ก)", product_buy_special_price),
        ("ซื้อ X แถม X (เลย์แมกซ์)", product_buy_get_free),
        ("ไม่มีโปรเลย", product_no_promo),
        ("ruleType แปลก ๆ ไม่รู้จักเลย", product_unknown_rule),
        ("ซื้อครบ X ลดทันที X (จินดา)", product_spend_threshold),
        ("bxtpgd แต่ parse ไม่ได้", product_spend_threshold_unparseable),
    ]

    for label, product in test_products:
        print(f"=== {label} ===")
        result = classify_promotion(product)
        print(result)
        print()

    print("=== ทดสอบ filter_products_with_promotion() ===")
    all_products = [p for _, p in test_products]
    filtered = filter_products_with_promotion(all_products)
    print(f"จาก {len(all_products)} ชิ้น เหลือที่มีโปรจริง {len(filtered)} ชิ้น:")
    for p in filtered:
        print(f"  - {p['name']}: {p['promotion_info']['type']} -> {p['promotion_info']['summary_text']}")