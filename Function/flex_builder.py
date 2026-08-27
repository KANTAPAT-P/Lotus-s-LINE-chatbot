"""
flex_builder.py
--------------------------------
แปลง view model (จาก product_view_model.py) เป็น Flex Message จริงที่
ส่งเข้า LINE ได้เลย ไฟล์นี้ไม่ต้องรู้เรื่อง promotions[]/ruleType/regex
อะไรเลย รู้แค่ view model schema เดียว ({name, image_url, link,
price_current, price_original, badge}) ทำให้ปรับ layout/สี/ขนาด
ทีหลังได้โดยไม่กระทบ logic การจำแนกโปรโมชั่น
"""

from linebot.models import (
    FlexSendMessage,
    BubbleContainer,
    CarouselContainer,
    BoxComponent,
    ImageComponent,
    TextComponent,
    SeparatorComponent,
    ButtonComponent,
    URIAction,
)

PLACEHOLDER_IMAGE = "https://via.placeholder.com/600x400.png?text=Lotus%27s"
BRAND_COLOR = "#00A651"  # เขียว Lotus's (ใช้กับปุ่ม/ราคาเน้น)


def build_bubble(view_model: dict) -> BubbleContainer:
    """
    สร้าง Bubble (การ์ด 1 ใบ) จาก view model 1 ชิ้น
    รองรับทั้ง 4 แบบ (ธรรมดา / ลด% / ซื้อ X ราคาพิเศษ / ซื้อ X แถม X)
    ด้วย field เดียวกันหมด ต่างกันแค่ "badge" มีหรือไม่มี และ
    "price_original" มีหรือไม่มี
    """
    name = view_model.get("name") or ""
    image_url = view_model.get("image_url") or PLACEHOLDER_IMAGE
    link = view_model.get("link")
    price_current = view_model.get("price_current")
    price_original = view_model.get("price_original")
    badge = view_model.get("badge")

    # ตัดชื่อสินค้าไม่ให้ยาวเกินไปจนล้น bubble (กันชื่อยาว ๆ ที่เจอจริง
    # เช่น "โลตัส ชุดเนื้อสไลซ์ปาร์ตี้ 800 กรัม" ยังพอไหว แต่บางชื่อยาวกว่านี้เยอะ)
    display_name = name if len(name) <= 60 else name[:57] + "..."

    # ปุ่ม/แอ็คชันเปิดลิงก์ ใช้ได้เฉพาะตอนมีลิงก์จริง (LINE error ถ้า uri ว่าง)
    hero_action = URIAction(label=display_name[:20] or "ดูสินค้า", uri=link) if link else None

    # ---------- ส่วนราคา ----------
    price_contents = []
    if price_original is not None and price_current is not None and price_original != price_current:
        # แบบลด % -> โชว์ราคาเดิมขีดฆ่า + ราคาใหม่เด่น ๆ
        price_contents.append(
            TextComponent(text=f"{price_original} บาท", size="sm", color="#999999", decoration="line-through")
        )
        price_contents.append(
            TextComponent(text=f"{price_current} บาท", size="xl", weight="bold", color="#E4002B")
        )
    else:
        # แบบธรรมดา / แบบ 3-4 ที่ราคาต่อชิ้นไม่ได้ลด -> โชว์ราคาเดียวเฉย ๆ
        price_text = f"{price_current} บาท" if price_current is not None else "สอบถามราคาที่สาขา"
        price_contents.append(TextComponent(text=price_text, size="xl", weight="bold", color=BRAND_COLOR))

    # ---------- ส่วน badge โปรโมชั่น (มีเฉพาะตอนมีโปรเท่านั้น) ----------
    body_contents = [
        TextComponent(text=display_name, weight="bold", size="md", wrap=True),
    ]

    if badge:
        body_contents.append(
            BoxComponent(
                layout="vertical",
                background_color=badge["color"],
                corner_radius="6px",
                padding_all="6px",
                margin="sm",
                contents=[
                    TextComponent(text=badge["text"], size="xs", color="#FFFFFF", weight="bold", align="center", wrap=True)
                ],
            )
        )

    body_contents.append(SeparatorComponent(margin="md"))
    body_contents.append(
        BoxComponent(layout="vertical", margin="md", contents=price_contents)
    )

    bubble_kwargs = dict(
        hero=ImageComponent(
            url=image_url,
            size="full",
            aspect_ratio="20:13",
            aspect_mode="cover",
            action=hero_action,
        ),
        body=BoxComponent(layout="vertical", spacing="sm", contents=body_contents),
    )

    # ปุ่ม "ดูสินค้านี้" ที่ footer ใช้ได้เฉพาะตอนมีลิงก์เหมือนกัน
    if link:
        bubble_kwargs["footer"] = BoxComponent(
            layout="vertical",
            spacing="sm",
            contents=[
                ButtonComponent(
                    style="primary",
                    color=BRAND_COLOR,
                    height="sm",
                    action=URIAction(label="ดูสินค้านี้บนเว็บไซต์", uri=link),
                )
            ],
        )

    return BubbleContainer(**bubble_kwargs)


def build_flex_reply(view_models: list) -> FlexSendMessage:
    """
    รับ list ของ view model (สูงสุด 5 ชิ้นจาก top5_selector.py แต่เผื่อ
    ตัดที่ 10 ไว้เป็น safety net เพราะ LINE จำกัด Carousel ไว้ที่ 12
    bubble ต่อ 1 ข้อความ) คืนค่าเป็น FlexSendMessage พร้อมส่งเข้า LINE
    """
    if not view_models:
        raise ValueError("view_models ว่างเปล่า ไม่มีอะไรให้สร้าง Flex Message")

    if len(view_models) == 1:
        contents = build_bubble(view_models[0])
        alt_text = view_models[0]["name"]
    else:
        contents = CarouselContainer(contents=[build_bubble(vm) for vm in view_models[:10]])
        alt_text = f"พบสินค้าที่เกี่ยวข้อง {len(view_models)} รายการ"

    return FlexSendMessage(alt_text=alt_text, contents=contents)


# ----------------------------------
# ทดสอบเดี่ยว ๆ ด้วย view model ทั้ง 4 แบบ
# ----------------------------------
if __name__ == "__main__":
    import json
    from product_view_model import build_view_model

    products = [
        {  # แบบ 1: ธรรมดา
            "name": "น้ำดื่มสิงห์ 600 มล.", "sku": "12345678",
            "thumbnail": {"url": "https://example.com/water.jpg"},
            "finalPricePerUOW": 7, "regularPricePerUOW": 7,
            "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
            "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
        },
        {  # แบบ 2: ลด %
            "name": "เทสโต แผ่นหยัก กลิ่นหมึกย่างทะเลเดือด 40 กรัม แพ็ค 6", "sku": "75723319",
            "thumbnail": {"url": "https://o2o-static.lotuss.com/products/86593/75723319.jpg"},
            "finalPricePerUOW": 79, "regularPricePerUOW": 99,
            "priceRange": {"minimumPrice": {"discount": {"amountOff": 20, "percentOff": 20.2}}},
            "promotions": [], "autoBadge": {"imagePromotion": {"items": []}},
        },
        {  # แบบ 3: ซื้อ X ราคาพิเศษ
            "name": "โค้ก ซีโร่ ซีโร่ 325 มล. แพ็ค 6", "sku": "171472571",
            "thumbnail": {"url": "https://o2o-static.lotuss.com/products/91129/171472571.jpg"},
            "finalPricePerUOW": 78, "regularPricePerUOW": 78,
            "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
            "promotions": [{"offerText": "Promotion Badge", "ruleType": "bxf"}],
            "autoBadge": {"imagePromotion": {"items": [
                {"items": [{"description": "ซื้อ 2 ชิ้น 153.0 บาท", "ruleType": "bxf"}], "name": "promotionRpm"}
            ]}},
        },
        {  # แบบ 4: ซื้อ X แถม X
            "name": "เลย์แมกซ์ กลิ่นปูผัดผงกะหรี่ ปูอัดกรอบ 60 กรัม", "sku": "75730961",
            "thumbnail": {"url": "https://o2o-static.lotuss.com/products/86593/75730961.jpg"},
            "finalPricePerUOW": 31, "regularPricePerUOW": 31,
            "priceRange": {"minimumPrice": {"discount": {"amountOff": 0, "percentOff": 0}}},
            "promotions": [{"offerText": "Promotion Badge", "ruleType": "bxgx"}],
            "autoBadge": {"imagePromotion": {"items": [
                {"items": [{"description": "ซื้อ 2 แถม 1", "ruleType": "bxgx"}], "name": "promotionRpm"}
            ]}},
        },
    ]

    view_models = [build_view_model(p) for p in products]

    print("=== ทดสอบสร้าง bubble ทีละใบ (เช็คว่าไม่ error) ===\n")
    for vm in view_models:
        bubble = build_bubble(vm)
        print(f"สร้าง bubble สำเร็จ: {vm['name'][:40]}")

    print("\n=== ทดสอบสร้าง Flex Message เต็มรูปแบบ (Carousel 4 ใบ) ===\n")
    flex_message = build_flex_reply(view_models)
    print(f"alt_text: {flex_message.alt_text}")

    # แปลงเป็น JSON ดูโครงสร้างจริงที่จะส่งเข้า LINE (ตัดมาแค่บางส่วนไม่ให้ยาวเกิน)
    flex_dict = flex_message.as_json_dict()
    print(f"\nจำนวน bubble ใน carousel: {len(flex_dict['contents']['contents'])}")
    print("\nตัวอย่าง bubble แรก (แบบธรรมดา ไม่มี badge):")
    print(json.dumps(flex_dict["contents"]["contents"][0]["body"], ensure_ascii=False, indent=2)[:600])

    print("\n\nตัวอย่าง bubble ที่ 2 (แบบลด % มี badge + ราคาขีดฆ่า):")
    print(json.dumps(flex_dict["contents"]["contents"][1]["body"], ensure_ascii=False, indent=2)[:800])