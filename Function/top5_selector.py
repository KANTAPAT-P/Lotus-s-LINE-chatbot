"""
top5_selector.py
--------------------------------
สุ่มเลือกสินค้า 5 ชิ้นจากรายการสินค้าทั้งหมดในหมวดหมู่ที่ค้นเจอ (จาก
lotus_searching.py) เพื่อโชว์เป็น Carousel ใน LINE

ตามเกณฑ์ "Randomization Fairness": อัลกอริทึมต้องไม่ติด Loop ดึงสินค้า
เดิมขึ้นมาแสดงบ่อยเกินไปตอนรีเฟรช/ถามซ้ำ จึงออกแบบให้จำไว้ว่าไม่กี่
รอบล่าสุดที่ผ่านมา เคยสุ่มโชว์ id อะไรไปแล้วบ้าง (แยกเก็บตามหมวดหมู่)
แล้วพยายามเลี่ยงไม่เอาสินค้าชุดนั้นมาซ้ำก่อน ถ้าสินค้าที่ไม่ซ้ำเหลือ
ไม่พอ 5 ชิ้น (หมวดมีสินค้ารวมน้อย) ค่อยยอมเติมจากที่เคยโชว์แล้ว

หมายเหตุข้อจำกัด: ประวัติที่จำไว้อยู่ใน "หน่วยความจำของ process"
เท่านั้น (module-level dict) ถ้า webhook_server restart ประวัติจะ
หายไป และถ้ารันแบบหลาย worker process พร้อมกัน (เช่น gunicorn -w 4)
แต่ละ worker จะมีประวัติแยกกันคนละชุด ไม่ได้ share กัน — ยอมรับได้
สำหรับ requirement นี้ เพราะจุดประสงค์แค่กันสินค้าชุดเดิมโผล่ซ้ำถี่ ๆ
ไม่ใช่ requirement ที่ต้อง persist ข้ามการ restart

--------------------------------
บันทึกการออกแบบ: get_top5_with_promotion() (เพิ่มทีหลัง)
--------------------------------
กรณี intent = ask_promotion ผสมกับ entity (เช่น "น้ำปลาโปรโมชั่น")
อยากให้ "สินค้าที่มีโปร" ถูกเลือกก่อนเป็นอันดับแรก ถ้าไม่ครบ 5 ชิ้น
ค่อยเติมจากสินค้าที่ไม่มีโปรให้ครบ

จุดที่ต้องระวัง: get_top5() เดิม "เลือก" และ "บันทึกประวัติกันซ้ำ"
อยู่ในฟังก์ชันเดียวกัน ถ้าเรียกซ้อนกัน 2 รอบ (รอบหาโปร + รอบหาของเติม)
จะบันทึกประวัติทับกันมั่ว (รอบหลังจะเห็นว่ารอบแรกเป็น "เพิ่งโชว์" ทั้ง
ที่ยังไม่ได้ตัดสินใจว่าจะเอาจริงไหม) จึงต้องแยก "การเลือก" ออกจาก
"การบันทึกประวัติ" เป็นคนละขั้นตอน (_sample_avoiding_recent ไม่บันทึก
ประวัติเอง ให้ผู้เรียกเป็นคนบันทึกทีเดียวตอนจบด้วย _record_shown)
"""

import random
from collections import defaultdict, deque

TOP_N = 5

# จำผลการสุ่ม "กี่รอบล่าสุด" ต่อหมวดหมู่ ยิ่งมากยิ่งกันซ้ำได้นานขึ้น
# แต่ก็ยิ่งต้องมีสินค้าในหมวดเยอะพอถึงจะมีของให้เลี่ยงจริง
_RECENT_HISTORY_SIZE = 3

# key = category_id, value = deque ของ set(id สินค้าที่เคยสุ่มโชว์)
# แต่ละ set คือผลลัพธ์ 1 รอบ เก็บย้อนหลังแค่ _RECENT_HISTORY_SIZE รอบ
_recent_shown = defaultdict(lambda: deque(maxlen=_RECENT_HISTORY_SIZE))


def _recent_ids_for(category_id) -> set:
    """รวม id สินค้าที่เพิ่งโชว์ไปในไม่กี่รอบล่าสุดของหมวดนี้"""
    recent_ids = set()
    for shown_batch in _recent_shown[category_id]:
        recent_ids.update(shown_batch)
    return recent_ids


def _record_shown(category_id, selected: list):
    """บันทึกว่ารอบนี้ (สุดท้ายจริง ๆ ที่จะส่งให้ user เห็น) โชว์ id อะไรไปบ้าง"""
    shown_ids = {p.get("id") for p in selected}
    _recent_shown[category_id].append(shown_ids)


def _sample_avoiding_recent(pool: list, count: int, recent_ids: set) -> list:
    """
    เลือกสินค้าจาก pool มา count ชิ้น โดยพยายามเลี่ยงตัวที่อยู่ใน
    recent_ids ก่อน ถ้าไม่พอค่อยเติมจากที่เหลือ (ที่อยู่ใน recent_ids)
    *** ฟังก์ชันนี้ไม่บันทึกประวัติเอง *** (แยกออกมาเป็นขั้นตอนเดียว
    ที่ทำได้แค่ "เลือก" เพื่อให้เรียกซ้อนกันหลายรอบได้อย่างปลอดภัย
    เช่นตอนต้องเลือกจาก 2 กลุ่ม (โปร + ไม่มีโปร) แยกกัน)
    คืน list ที่มีจำนวน <= count เสมอ (น้อยกว่าได้ถ้า pool มีไม่พอ)
    """
    if count <= 0 or not pool:
        return []

    fresh_pool = [p for p in pool if p.get("id") not in recent_ids]
    stale_pool = [p for p in pool if p.get("id") in recent_ids]

    if len(fresh_pool) >= count:
        return random.sample(fresh_pool, count)

    selected = fresh_pool[:]
    need = count - len(selected)
    selected.extend(random.sample(stale_pool, min(need, len(stale_pool))))
    return selected


def get_top5(category_id, products):
    """
    รับ category_id (ใช้เป็น key เก็บประวัติการสุ่ม) และ products
    (list สินค้าทั้งหมดในหมวดนั้น จาก lotus_searching.py)
    คืนค่าเป็น list สินค้าที่สุ่มมาสูงสุด 5 ชิ้น (น้อยกว่านั้นได้ถ้า
    หมวดมีสินค้าไม่ถึง 5 ชิ้นจริง ๆ)
    """
    if not products:
        return []

    # หมวดมีสินค้าน้อยกว่าหรือเท่ากับ 5 -> คืนทั้งหมดเลย ไม่มีอะไรให้เลือก
    # แค่สลับลำดับเพื่อไม่ให้โชว์เรียงเหมือนเดิมทุกครั้ง (ไม่ต้องบันทึก
    # ประวัติ เพราะยังไงก็โชว์ทั้งหมดทุกครั้งอยู่ดี ไม่มีอะไรให้เลี่ยง)
    if len(products) <= TOP_N:
        selected = products[:]
        random.shuffle(selected)
        return selected

    recent_ids = _recent_ids_for(category_id)
    print(f"[top5_selector] category_id={category_id}: สินค้าทั้งหมด {len(products)} ชิ้น, "
          f"เคยโชว์ไปแล้วในรอบล่าสุด {len(recent_ids)} ชิ้น")

    selected = _sample_avoiding_recent(products, TOP_N, recent_ids)
    random.shuffle(selected)  # กันเรียงลำดับเดิมซ้ำ ๆ แม้ตัวสินค้าจะต่างกัน

    _record_shown(category_id, selected)
    print(f"[top5_selector] เลือกได้ {len(selected)} ชิ้น: {[p.get('name') for p in selected]}")

    return selected


def get_top5_with_promotion(category_id, products, want_promotion: bool):
    """
    เหมือน get_top5() แต่ถ้า want_promotion=True (เช่น user พิมพ์
    "น้ำปลาโปรโมชั่น" -> intent=ask_promotion + entity="น้ำปลา") จะ
    เลือก "สินค้าที่มีโปร" มาก่อนเป็นอันดับแรก ถ้าไม่ครบ 5 ชิ้น ค่อย
    เติมจากสินค้าที่ไม่มีโปรให้ครบ 5 (ดีกว่าโชว์ไม่ครบ 5 ชิ้น)

    ถ้า want_promotion=False หรือหมวดนี้ไม่มีสินค้ามีโปรเลยสักชิ้น
    -> ทำงานเหมือน get_top5() ปกติทุกอย่าง (fallback อัตโนมัติ)
    """
    if not want_promotion:
        return get_top5(category_id, products)

    if not products:
        return []

    # import ในฟังก์ชันกันปัญหา circular import (promotion_parser.py
    # ไม่ได้ import top5_selector.py กลับมา แต่กันไว้เผื่ออนาคต)
    from promotion_parser import filter_products_with_promotion

    promo_products = filter_products_with_promotion(products)

    if not promo_products:
        print(f"[top5_selector] category_id={category_id}: ขอกรองเฉพาะโปรโมชั่น "
              f"แต่หมวดนี้ไม่มีสินค้าที่มีโปรเลย -> ใช้สินค้าทั้งหมดแทน (fallback)")
        return get_top5(category_id, products)

    recent_ids = _recent_ids_for(category_id)

    if len(promo_products) <= TOP_N:
        # โปรมีน้อยกว่าหรือเท่ากับ 5 -> เอามาหมดเลย ไม่ต้องสุ่มตัดออก
        promo_selected = promo_products[:]
    else:
        promo_selected = _sample_avoiding_recent(promo_products, TOP_N, recent_ids)

    need = TOP_N - len(promo_selected)

    if need > 0:
        print(f"[top5_selector] category_id={category_id}: เจอสินค้ามีโปร {len(promo_products)} ชิ้น "
              f"(ไม่ครบ {TOP_N}) -> เติมจากสินค้าที่ไม่มีโปรอีก {need} ชิ้น")
        promo_ids = {p.get("id") for p in promo_selected}
        non_promo_pool = [p for p in products if p.get("id") not in promo_ids]
        filler = _sample_avoiding_recent(non_promo_pool, need, recent_ids)
    else:
        filler = []

    combined = promo_selected + filler
    random.shuffle(combined)

    _record_shown(category_id, combined)
    print(f"[top5_selector] เลือกได้ {len(combined)} ชิ้น (มีโปร {len(promo_selected)}, เติม {len(filler)}): "
          f"{[p.get('name') for p in combined]}")

    return combined


def get_top5_by_price(products: list, ascending: bool = True):
    """
    เรียงสินค้าตามราคา (finalPricePerUOW) แล้วคืนมาสูงสุด 5 ชิ้นแรก
    ascending=True -> ถูกสุดก่อน, False -> แพงสุดก่อน

    ใช้กับปุ่ม Quick Reply "ถูกสุด"/"แพงสุด" ที่แนบไปกับผลการค้นหา
    ไม่ผ่านกลไกกันซ้ำของ get_top5() เพราะจุดประสงค์ต่างกัน (ตรงนี้
    ต้องการผลลัพธ์ "แน่นอนตายตัว" ตามราคาจริง ไม่ใช่สุ่ม)

    สินค้าที่ไม่มี field ราคา (finalPricePerUOW เป็น None หรือไม่มี
    เลย) จะถูกตัดออกไปเลย ไม่เอามาเรียงปนด้วย (กันเรียงผิดเพราะไม่มี
    ราคาจริงให้เทียบ)
    """
    priced_products = [p for p in products if p.get("finalPricePerUOW") is not None]

    if not priced_products:
        print("[top5_selector] ไม่มีสินค้าไหนมีราคาให้เรียงเลย")
        return []

    sorted_products = sorted(
        priced_products,
        key=lambda p: p["finalPricePerUOW"],
        reverse=not ascending,
    )

    result = sorted_products[:TOP_N]
    direction = "ถูกสุด" if ascending else "แพงสุด"
    print(f"[top5_selector] เรียงตามราคา ({direction}) ได้ {len(result)} ชิ้น: "
          f"{[(p.get('name'), p.get('finalPricePerUOW')) for p in result]}")

    return result


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    # จำลองสินค้า 12 ชิ้นในหมวดเดียวกัน
    mock_products = [
        {"id": i, "name": f"สินค้าทดสอบ #{i}"} for i in range(1, 13)
    ]

    print("=== ทดสอบสุ่ม 5 รอบติดกัน ในหมวดเดียวกัน (category_id=999) ===\n")
    for round_num in range(1, 6):
        print(f"--- รอบที่ {round_num} ---")
        top5 = get_top5(999, mock_products)
        ids_shown = sorted(p["id"] for p in top5)
        print(f"id ที่ได้: {ids_shown}\n")

    print("=== ทดสอบหมวดที่มีสินค้าน้อยกว่า 5 ชิ้น (category_id=1, มี 3 ชิ้น) ===\n")
    small_products = [{"id": i, "name": f"ของหายาก #{i}"} for i in range(1, 4)]
    for round_num in range(1, 3):
        top5 = get_top5(1, small_products)
        print(f"รอบที่ {round_num}: ได้ {len(top5)} ชิ้น -> {[p['name'] for p in top5]}")

    # ---------- ทดสอบ get_top5_with_promotion() ----------
    print("\n" + "=" * 60)
    print("=== ทดสอบ get_top5_with_promotion() ===")
    print("=" * 60)

    def make_product(pid, name, has_promo, rule_type="bxgx"):
        """สร้างสินค้าจำลอง กำหนดได้ว่าให้มีโปรหรือไม่ (สำหรับเทส)"""
        product = {
            "id": pid, "name": name,
            "regularPricePerUOW": 100, "finalPricePerUOW": 100,
            "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
            "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
        }
        if has_promo:
            product["promotions"] = [{"offerText": "Promo", "ruleType": rule_type}]
            product["autoBadge"]["imagePromotion"]["items"] = [
                {"items": [{"description": "ซื้อ 2 แถม 1", "ruleType": rule_type}], "name": "promotionRpm"}
            ]
        return product

    # เคส A: หมวดมีสินค้ามีโปรแค่ 2 ชิ้น จาก 10 ชิ้น (ต้องเติมของไม่มีโปร 3 ชิ้น)
    print("\n--- เคส A: มีโปรแค่ 2 จาก 10 ชิ้น (ต้องเติม 3) ---")
    products_a = [make_product(i, f"สินค้า A#{i}", has_promo=(i <= 2)) for i in range(1, 11)]
    result_a = get_top5_with_promotion(2001, products_a, want_promotion=True)
    promo_count = sum(1 for p in result_a if p.get("promotion_info"))
    print(f"ได้ {len(result_a)} ชิ้น, มีโปร {promo_count} ชิ้น, "
          f"ชื่อ: {[p['name'] for p in result_a]}")

    # เคส B: หมวดมีสินค้ามีโปรเกิน 5 ชิ้น (ควรได้ครบ 5 จากที่มีโปรล้วน ๆ)
    print("\n--- เคส B: มีโปร 8 จาก 10 ชิ้น (เกิน 5 พอดี) ---")
    products_b = [make_product(i, f"สินค้า B#{i}", has_promo=(i <= 8)) for i in range(1, 11)]
    result_b = get_top5_with_promotion(2002, products_b, want_promotion=True)
    promo_count = sum(1 for p in result_b if p.get("promotion_info"))
    print(f"ได้ {len(result_b)} ชิ้น, มีโปรทั้งหมด {promo_count} ชิ้น (ควรเป็น 5)")

    # เคส C: หมวดไม่มีสินค้ามีโปรเลยสักชิ้น -> ต้อง fallback เป็น get_top5 ปกติ
    print("\n--- เคส C: ไม่มีโปรเลยสักชิ้น (ต้อง fallback) ---")
    products_c = [make_product(i, f"สินค้า C#{i}", has_promo=False) for i in range(1, 11)]
    result_c = get_top5_with_promotion(2003, products_c, want_promotion=True)
    print(f"ได้ {len(result_c)} ชิ้น (fallback เป็น top5 ปกติ ไม่มี promotion_info เลย)")

    # เคส D: want_promotion=False -> ต้องทำงานเหมือน get_top5() เป๊ะ
    print("\n--- เคส D: want_promotion=False (ควรเหมือน get_top5 ปกติ) ---")
    result_d = get_top5_with_promotion(2004, products_a, want_promotion=False)
    print(f"ได้ {len(result_d)} ชิ้น (ไม่สนใจโปรเลย)")