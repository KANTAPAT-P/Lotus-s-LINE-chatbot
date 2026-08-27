"""
webhook_server.py
--------------------------------
จุดรับ-ส่งข้อความจาก LINE เข้า-ออก รวม pipeline ทั้งหมดที่เขียนแยกไว้
ก่อนหน้านี้เข้าด้วยกัน:

    text_processor.py (intent + entity)
        │
        ├── entity เจอ ในหมวดหมู่ (local data/all_product/)
        │     → lotus_searching.py
        │     → ถ้า status="found": top5_selector.get_top5_with_promotion()
        │     → ถ้า status="not_found": ตอบว่าของหมด
        │     → ถ้า status="error": fallback ไปค้นสด (เหมือน entity ไม่เจอ)
        │
        └── entity ไม่เจอ (เช่นเป็นชื่อแบรนด์ ไม่ใช่ชื่อหมวด) หรือ local error
              → scrap_current_product.py ค้นหาสดจาก lotus (ใช้ entity_search_text
                ที่ตัด intent keyword ออกแล้ว ไม่ใช่ข้อความดิบทั้งประโยค)
              → ถ้า status="found": top5_selector.get_top5_with_promotion()
                (ใช้ "live:<คำค้น>" เป็น key แทน category_id จริงเพราะไม่มี)
              → ถ้า status="not_found"/"error": ตอบ fallback message

    ทั้ง 2 เส้นทางมาบรรจบกันที่ product_view_model.build_view_models()
    แล้วส่งต่อ flex_builder.build_flex_reply() เป็นขั้นตอนสุดท้ายเสมอ

--------------------------------
บันทึกการออกแบบ: แยก generate_reply() ออกจาก handle_message()
--------------------------------
generate_reply(user_message) คืนค่าเป็น "list ของ SendMessage" เสมอ
(ไม่ใช่ message เดียว) ไม่แตะ LINE API เลย (ไม่เรียก reply_message,
ไม่ต้องมี event) เพื่อให้เทส logic การ route ทั้งหมดได้โดยไม่ต้องมี
LINE credentials จริง หรือรัน Flask server จริง — handle_message() แค่
เอา list ที่ได้ไปยิงเข้า LINE อีกที

--------------------------------
บันทึกการออกแบบ: ตอบเป็นหลายข้อความในการ reply ครั้งเดียว
--------------------------------
LINE Messaging API รับ "list ของข้อความสูงสุด 5 ข้อความ" ในการเรียก
reply_message() ครั้งเดียวได้ (ดู doc ของ line-bot-sdk: `messages: T |
list[T], Max: 5`) เลยใช้ตรงนี้ทำให้การตอบดูมีขั้นตอนมากขึ้น โดยไม่ต้อง
พึ่ง push message (ที่มี quota จำกัด) หรือแก้ปัญหา reply token ใช้ได้
ครั้งเดียว — ส่งพร้อมกันเป็น list เลย:
    ["ระบบกำลังค้นหาสินค้า", "ตรวจพบ X รายการ แสดงผล 5 รายการ...", flex]
LINE จะโชว์เป็น 3 บับเบิลข้อความเรียงต่อกันในแชท (แม้จะมาถึงพร้อมกัน
จริง ๆ ไม่ได้หน่วงเวลาจริงระหว่างข้อความ แต่ก็ให้ความรู้สึกเป็นขั้นตอน
ต่อเนื่องกันในหน้าแชท) ส่วนข้อความ "⚙️ระบบกำลังประมวลผลข้อความผู้ใช้⚙️"
ที่โชว์ก่อนหน้านั้นมาจาก Auto-response feature ของ LINE OA Manager
(ตั้งค่าแยกไว้ต่างหาก ทำงานอิสระ ไม่ผ่าน webhook นี้เลย)

--------------------------------
บันทึกการออกแบบ: Quick Reply ต่อท้าย flex message (ปุ่ม "ขอดูโปรโมชั่น"/
"ถูกสุด"/"แพงสุด")
--------------------------------
หลังตอบผลการค้นหาแล้ว แนบปุ่ม Quick Reply ไปกับ flex message (ข้อความ
สุดท้ายใน list) ให้ user กดต่อได้เลยโดยไม่ต้องพิมพ์ใหม่ ใช้ Postback
Action (ไม่ใช่ Text Action) เพราะปุ่มแบบ "ถูกสุด"/"แพงสุด" ต้อง "รู้"
ว่าหมายถึงหมวดไหน — LINE ไม่มีความจำบทสนทนาให้อัตโนมัติ จึงต้องฝัง
"key" (category_id หรือ "live:<คำค้น>") ไปในข้อมูล postback โดยตรง
เช่น "promo:98345", "price_asc:live:เลย์" แล้วพอ user กด จะเป็น
webhook event คนละประเภท (PostbackEvent ไม่ใช่ MessageEvent) ต้องมี
handler แยกต่างหาก (ดู handle_postback() ด้านล่าง) ซึ่งจะ "ค้นหาใหม่"
จาก key ที่ฝังมา (เปิดไฟล์ local ซ้ำ หรือยิง live search ซ้ำ) แล้ว
กรอง/เรียงตามปุ่มที่กด ไม่ได้เก็บ state ของสินค้าจากรอบแรกไว้เลย
(เพราะ HTTP request แต่ละครั้งไม่มี state ผูกกัน ต้องคิดจากศูนย์ใหม่
ทุกครั้งโดยอาศัย key ที่ฝังไว้เป็นตัวเชื่อมเดียว)
"""

import os
import sys

# ----------------------------------
# เติม path ให้ import ข้ามโฟลเดอร์ได้ (โปรเจกต์แยกเป็นหลายโฟลเดอร์
# AI_text_processing/, Function/, scraping/ ไม่ได้ทำเป็น package
# จึงต้องเติม sys.path เอง ก่อน import โมดูลข้ามโฟลเดอร์)
# ----------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
for folder in ("AI_text_processing", "Function", "scraping"):
    sys.path.append(os.path.join(PROJECT_ROOT, folder))
sys.path.append(PROJECT_ROOT)  # เผื่อ config.py อยู่ตรงราก

from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, QuickReply, QuickReplyButton, PostbackAction,
)

from text_processor import process_message
from lotus_searching import search_from_entity, search_by_category_id
from top5_selector import get_top5_with_promotion, get_top5_by_price
from product_view_model import build_view_models
from flex_builder import build_flex_reply
from scrap_current_product import search_products_status

# ----------------------------------
# Load Environment Variables
# ----------------------------------
load_dotenv()

CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

# ----------------------------------
# Flask + LINE
# ----------------------------------
app = Flask(__name__)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ----------------------------------
# ข้อความ fallback ต่าง ๆ (รวมไว้ที่เดียวให้แก้ง่าย)
# ----------------------------------
MSG_GREETING = (
    "สวัสดีครับ 👋 พิมพ์ชื่อสินค้าที่ต้องการค้นหาได้เลยครับ "
    "เช่น 'น้ำปลา' หรือ 'ซอสมะเขือเทศ' หรือถามโปรโมชั่นได้เลยครับ"
)
MSG_NOT_FOUND = (
    "ไม่พบสินค้าที่เกี่ยวข้องกับคำถามนี้ครับ "
    "ลองพิมพ์ชื่อสินค้าหรือหมวดหมู่ เช่น 'น้ำปลา' หรือ 'เบอร์เกอร์' ดูนะครับ"
)
MSG_CATEGORY_EMPTY = "ตอนนี้หมวด '{category_name}' ไม่มีสินค้าเลยครับ ลองถามหมวดอื่นดูนะครับ"
MSG_NO_PROMOTION_KEYWORD = (
    "ลองพิมพ์ชื่อสินค้าที่อยากดูโปรโมชั่นด้วยนะครับ "
    "เช่น 'น้ำยาซักผ้ามีโปรไหม' หรือ 'น้ำปลาโปรโมชั่น'"
)
MSG_SYSTEM_ERROR = "ขออภัยครับ ระบบค้นหาขัดข้อง ลองใหม่อีกครั้งนะครับ"
MSG_FALLBACK_NOTICE = "กำลังค้นหาเพิ่มเติมจากเว็บไซต์ Lotus's โดยตรง: https://www.lotuss.com/th/search/"


def _search_local_or_live(entity: dict, entity_search_text: str, intent: str):
    """
    รวม logic การหา "แหล่งสินค้า" ทั้ง 2 เส้นทาง (local ก่อน, ไม่เจอ
    ค่อย fallback ไปค้นสด) ไว้ในที่เดียว คืนค่าเป็น tuple:
        (products, key_for_top5, error_message, used_fallback)

    ถ้า error_message ไม่ใช่ None แปลว่าจบตรงนี้เลย ไม่ต้องทำอะไรต่อ
    ให้ webhook_server.py ตอบ error_message กลับไปได้เลย
    key_for_top5 คือ "key" ที่ top5_selector.py ใช้เก็บประวัติกันซ้ำ
    (เป็น category_id จริงถ้ามาจาก local, หรือ "live:<คำค้น>" ถ้ามา
    จากการค้นสด เพราะไม่มี category_id ให้ใช้)
    used_fallback บอกว่า "ผลลัพธ์นี้มาจากการค้นสด (True) หรือมาจาก
    หมวดหมู่ local โดยตรง (False)" เอาไว้ให้ generate_reply() ตัดสินใจ
    ว่าต้องแทรกข้อความแจ้ง user ว่ากำลังค้นสดอยู่ไหม
    """
    # ---------- เส้นทางที่ 1: entity เจอในหมวดหมู่ local ----------
    if entity["found"]:
        local_result = search_from_entity(entity)

        if local_result["status"] == "found":
            return local_result["products"], entity["category_id"], None, False

        if local_result["status"] == "not_found":
            msg = MSG_CATEGORY_EMPTY.format(category_name=entity["category_name"])
            return None, None, msg, False

        # status == "error" (ไฟล์หาย/อ่านไม่ได้) -> ไหลลงไป fallback ค้นสดด้านล่างต่อ
        print(f"[webhook_server] local search error สำหรับ category_id={entity['category_id']} "
              f"-> fallback ไปค้นสดแทน")

    # ---------- เส้นทางที่ 2: fallback ค้นสด (entity ไม่เจอ หรือ local error) ----------
    keyword = (entity_search_text or "").strip()

    if not keyword:
        # ไม่มีคำอะไรให้ค้นหาเลยจริง ๆ (เช่น "โปรโมชั่น" เดี่ยว ๆ ที่ตัด
        # intent keyword ออกแล้วไม่เหลืออะไรเลย) ค้นหาสดไปก็ไม่มีประโยชน์
        if intent == "ask_promotion":
            return None, None, MSG_NO_PROMOTION_KEYWORD, False
        return None, None, MSG_NOT_FOUND, False

    live_result = search_products_status(keyword)

    if live_result["status"] == "found":
        return live_result["products"], f"live:{keyword}", None, True

    if live_result["status"] == "not_found":
        return None, None, MSG_NOT_FOUND, True

    # status == "error" (timeout / network error ตอนค้นสด)
    return None, None, MSG_SYSTEM_ERROR, True


def _build_summary_text(total_found: int, view_models: list) -> str:
    """
    สร้างข้อความสรุปจำนวนสินค้า เช่น:
        ตรวจพบสินค้าทั้งหมด 8 รายการ แสดงผล 5 รายการ
          • สินค้าธรรมดา 3 รายการ
          • สินค้าที่มีโปรโมชั่น 2 รายการ

    นับ "สินค้าที่มีโปรโมชั่น" แบบรวมทุกแบบ (ลด %, ซื้อ X ราคาพิเศษ,
    ซื้อ X แถม X, อื่น ๆ) ไม่แยกย่อยตามประเภท เช็คง่าย ๆ จากว่า
    view_model["badge"] เป็น None หรือไม่ (badge มีก็ต่อเมื่อมีโปรจริง
    ตามที่ออกแบบไว้ใน product_view_model.py)
    """
    shown = len(view_models)
    promo_count = sum(1 for vm in view_models if vm.get("badge"))
    normal_count = shown - promo_count

    return (
        f"ตรวจพบสินค้าทั้งหมด {total_found} รายการ แสดงผล {shown} รายการ\n"
        f"  • สินค้าธรรมดา {normal_count} รายการ\n"
        f"  • สินค้าที่มีโปรโมชั่น {promo_count} รายการ"
    )


def _build_quick_reply(key) -> QuickReply:
    """
    สร้างปุ่ม Quick Reply 3 ปุ่ม: ขอดูโปรโมชั่น / ถูกสุด / แพงสุด
    ผูกกับ "key" เดียวกับที่ใช้ค้นหารอบนี้ (category_id หรือ
    "live:<คำค้น>") ฝังไปใน postback data เพื่อให้กดครั้งต่อไปแล้ว
    ระบบรู้ว่าต้องค้นหาใหม่จากหมวด/คำค้นไหน (ดู handle_postback())
    """
    return QuickReply(items=[
        QuickReplyButton(action=PostbackAction(
            label="ขอดูโปรโมชั่น", data=f"promo:{key}", display_text="ขอดูโปรโมชั่น",
        )),
        QuickReplyButton(action=PostbackAction(
            label="ถูกสุด", data=f"price_asc:{key}", display_text="ขอดูสินค้าราคาถูกสุด",
        )),
        QuickReplyButton(action=PostbackAction(
            label="แพงสุด", data=f"price_desc:{key}", display_text="ขอดูสินค้าราคาแพงสุด",
        )),
    ])


def _reconstruct_products(key: str):
    """
    รับ key (category_id เป็นตัวเลขล้วน ๆ หรือ "live:<คำค้น>") ค้นหา
    สินค้าใหม่จากศูนย์ (เปิดไฟล์ local ซ้ำ หรือยิง live search ซ้ำ)
    เพราะ postback event ไม่มี state ของสินค้าจากรอบแรกติดมาด้วยเลย
    คืนค่าเป็น (products, status)
    """
    if key.startswith("live:"):
        keyword = key[len("live:"):]
        result = search_products_status(keyword)
        return result.get("products", []), result["status"]

    try:
        category_id = int(key)
    except ValueError:
        print(f"[webhook_server] key {key!r} ไม่ใช่ category_id ตัวเลขและไม่ใช่ live: -> ผิดปกติ")
        return [], "error"

    result = search_by_category_id(category_id)
    return result.get("products", []), result["status"]


def generate_reply(user_message: str) -> list:
    """
    รับข้อความดิบจาก user คืนค่าเป็น "list ของ SendMessage" (1-4
    ข้อความ) พร้อมส่งเข้า LINE ผ่าน reply_message() ได้เลย (LINE รับ
    list สูงสุด 5 ข้อความในการ reply ครั้งเดียว) ไม่แตะ LINE API เอง
    (แยกออกมาต่างหากเพื่อให้เทสได้โดยไม่ต้องมี LINE credentials จริง)

    เคสตอบสั้น (greeting, error, not_found ฯลฯ) -> list มี 1 ข้อความ
    เคสตอบสำเร็จ จากหมวดหมู่ local -> list มี 3 ข้อความ:
        [1] "ระบบกำลังค้นหาสินค้า"
        [2] สรุปจำนวน (ทั้งหมด/แสดงผล/ธรรมดา/มีโปร)
        [3] Flex Message (carousel สินค้า)
    เคสตอบสำเร็จ จากการ fallback ค้นสด (entity ไม่เจอในหมวดหมู่ local)
    -> list มี 4 ข้อความ (แทรกข้อความแจ้งเตือนก่อนสรุปจำนวน):
        [1] "ระบบกำลังค้นหาสินค้า"
        [2] "ไม่พบหมวดหมู่ดังกล่าว ทำการค้นหาสินค้าโดยตรงจาก ..."
        [3] สรุปจำนวน
        [4] Flex Message
    """
    result = process_message(user_message)
    intent = result["intent"]
    entity = result["entity"]
    # ใช้ .get() แทนการ index ตรง ๆ กันปัญหา KeyError ถ้า text_processor.py
    # เป็นคนละเวอร์ชันกับที่ webhook_server.py คาดหวัง (เคยเจอปัญหานี้มาแล้ว
    # ตอน entity_search_text หายไปเพราะไฟล์เก่ากว่าที่คิดไว้)
    entity_search_text = result.get("entity_search_text", "")

    if intent == "greeting":
        return [TextSendMessage(text=MSG_GREETING)]

    products, top5_key, error_message, used_fallback = _search_local_or_live(
        entity, entity_search_text, intent
    )

    if error_message:
        return [TextSendMessage(text=error_message)]

    want_promotion = (intent == "ask_promotion")
    top5_products = get_top5_with_promotion(top5_key, products, want_promotion=want_promotion)

    if not top5_products:
        # เผื่อกรณีแปลก ๆ ที่ผ่านมาถึงตรงนี้ได้แต่ดันไม่มีสินค้าจริง
        return [TextSendMessage(text=MSG_NOT_FOUND)]

    view_models = build_view_models(top5_products)
    flex_message = build_flex_reply(view_models)
    flex_message.quick_reply = _build_quick_reply(top5_key)  # แนบปุ่มให้กดต่อได้เลย
    summary_text = _build_summary_text(total_found=len(products), view_models=view_models)

    messages = [TextSendMessage(text="ระบบกำลังค้นหาสินค้า")]
    if used_fallback:
        messages.append(TextSendMessage(text=MSG_FALLBACK_NOTICE))
    messages.append(TextSendMessage(text=summary_text))
    messages.append(flex_message)

    return messages


# ----------------------------------
# Webhook
# ----------------------------------
@app.route("/", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


# ----------------------------------
# Handle Text Message
# ----------------------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    print(f"[webhook_server] ได้รับข้อความ: {user_message!r}")

    try:
        reply = generate_reply(user_message)
    except Exception as e:
        # กันไม่ให้ error ตรงไหนก็ตามทำให้ webhook ค้างจนไม่ตอบอะไรเลย
        print(f"[webhook_server] เกิด error ไม่คาดคิดตอนสร้างคำตอบ: {e}")
        reply = [TextSendMessage(text=MSG_SYSTEM_ERROR)]

    line_bot_api.reply_message(event.reply_token, reply)


def generate_postback_reply(data: str) -> list:
    """
    รับ postback data ที่ฝัง action+key มาด้วย เช่น "promo:98345" หรือ
    "price_asc:live:เลย์" (สังเกตว่า key ของ live search มี ":" ซ้อน
    อยู่ข้างในเองด้วย จึง split ด้วย maxsplit=1 เท่านั้น ตัดแค่ตัวแรก)
    คืนค่าเป็น list ของ SendMessage เหมือน generate_reply() ปกติ
    """
    try:
        action, key = data.split(":", 1)
    except ValueError:
        print(f"[webhook_server] postback data {data!r} รูปแบบผิดปกติ (ไม่มี ':')")
        return [TextSendMessage(text=MSG_SYSTEM_ERROR)]

    products, status = _reconstruct_products(key)

    if status != "found" or not products:
        print(f"[webhook_server] postback: ค้นหาใหม่จาก key={key!r} แล้วไม่เจอสินค้า (status={status})")
        return [TextSendMessage(text=MSG_NOT_FOUND)]

    if action == "promo":
        selected = get_top5_with_promotion(key, products, want_promotion=True)
        if not selected:
            return [TextSendMessage(text="ตอนนี้หมวดนี้ไม่มีโปรโมชั่นเลยครับ")]
    elif action == "price_asc":
        selected = get_top5_by_price(products, ascending=True)
        if not selected:
            return [TextSendMessage(text="สินค้าในหมวดนี้ไม่มีราคาให้เปรียบเทียบเลยครับ")]
    elif action == "price_desc":
        selected = get_top5_by_price(products, ascending=False)
        if not selected:
            return [TextSendMessage(text="สินค้าในหมวดนี้ไม่มีราคาให้เปรียบเทียบเลยครับ")]
    else:
        print(f"[webhook_server] postback action {action!r} ไม่รู้จัก")
        return [TextSendMessage(text=MSG_SYSTEM_ERROR)]

    view_models = build_view_models(selected)
    flex_message = build_flex_reply(view_models)
    flex_message.quick_reply = _build_quick_reply(key)  # แนบปุ่มต่อให้กดต่อได้อีกเรื่อย ๆ

    return [flex_message]


# ----------------------------------
# Handle Postback (ปุ่ม Quick Reply: ขอดูโปรโมชั่น / ถูกสุด / แพงสุด)
# ----------------------------------
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    print(f"[webhook_server] ได้รับ postback: {data!r}")

    try:
        reply = generate_postback_reply(data)
    except Exception as e:
        print(f"[webhook_server] เกิด error ไม่คาดคิดตอนประมวลผล postback: {e}")
        reply = [TextSendMessage(text=MSG_SYSTEM_ERROR)]

    line_bot_api.reply_message(event.reply_token, reply)


# ----------------------------------
# Run Server
# ----------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)