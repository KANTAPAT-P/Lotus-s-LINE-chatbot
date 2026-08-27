"""
compare_intent.py
--------------------------------
ชุดข้อความทดสอบ (TEST_CASES) พร้อม Intent ที่ถูกต้อง (ground truth)
สำหรับเปรียบเทียบ Keyword Matching กับ Sentence-BERT (bert_intent.py)
ตามใบปฏิบัติการเรื่อง "เปรียบเทียบ Intent Detection ระหว่าง Keyword
Matching กับ Sentence-BERT"

รันไฟล์นี้ตรง ๆ เพื่อดูตารางเปรียบเทียบผลรายข้อความ + สรุปความแม่นยำ
(accuracy) ของทั้ง 2 วิธีเทียบกับ ground truth:

    python compare_intent.py

TEST_CASES ยังถูก import ไปใช้ใน webhook_server.py ด้วย เพื่อเช็คว่า
ข้อความที่ user พิมพ์เข้ามาจริง ๆ ตรงกับชุดทดสอบนี้ไหม (ถ้าตรง จะรู้
"Intent จริง" มาโชว์ใน log เทียบกับที่ระบบทำนายได้เลย ถ้าไม่ตรงจะโชว์
เป็น "-" แทนเพราะไม่มี label ล่วงหน้า)

--------------------------------
บันทึกสำคัญ: ฝั่ง Keyword ต้องใช้ text_processor.process_message()
ไม่ใช่ intent_detector.detect_intent() เดี่ยว ๆ
--------------------------------
ทดสอบรอบแรกเคยเรียก intent_detector.detect_intent() ตรง ๆ มาเทียบกับ
BERT ตรง ๆ แล้วผลออกมาว่า Keyword แพ้ BERT ขาดลอย (68.8% vs 93.8%)
แต่พอไล่ดูจริง ๆ พบว่า "ไม่แฟร์" เพราะในระบบของเรา intent "search_
product" เกิดจากการ "รวม" intent_detector (จับ greeting/ask_promotion)
เข้ากับ entity_extractor (จับชื่อสินค้า) ใน text_processor.py — ถ้า
เรียก intent_detector.detect_intent() เดี่ยว ๆ มันไม่มีทางตอบ "search_
product" ได้เลยสักเคส (ไม่ได้อยู่ใน INTENT_PRIORITY) เพราะฉะนั้นการ
เทียบที่ตรงกับระบบจริงต้องใช้ text_processor.process_message()["intent"]
ซึ่งคือ pipeline เต็มรูปแบบที่ใช้ตอบ user จริง ไม่ใช่แค่ intent_detector
เพียวๆ
"""

from text_processor import process_message
import bert_intent

# (ข้อความ, intent ที่ถูกต้อง) — ครอบคลุมทั้ง 4 intent ที่ระบบรองรับ
# (greeting, ask_promotion, search_product, unknown) รวมถึงเคสพิมพ์ผิด
# และเคสที่เคยเจอบั๊กมาก่อน (เช่น "โปรโมชั่น" เดี่ยว ๆ)
#
# หมายเหตุ: เคส search_product ต้องใช้ชื่อสินค้าที่ "มีอยู่จริง" ใน
# data/categories/categories_flat.json ถึงจะทดสอบฝั่ง Keyword ได้แฟร์
# (ถ้าลองเปลี่ยนชื่อสินค้าเป็นอย่างอื่นที่ไม่มีในหมวดหมู่จริง ฝั่ง
# Keyword จะตอบ unknown ทุกครั้งเพราะ entity_extractor หาไม่เจอ ไม่ใช่
# เพราะ logic ผิด)
TEST_CASES = [
    ("สวัสดีครับ", "greeting"),
    ("สวัสดีค่ะ", "greeting"),
    ("หวัดดีครับ", "greeting"),
    ("hello", "greeting"),
    ("มีโปรโมชั่นอะไรบ้าง", "ask_promotion"),
    ("วันนี้มีโปรโมชั่นไหม", "ask_promotion"),
    ("ลดราคาไหมวันนี้", "ask_promotion"),
    ("โปรโมชั่น", "ask_promotion"),
    ("มีดีลอะไรน่าสนใจไหม", "ask_promotion"),
    ("อยากได้น้ำปลา", "search_product"),
    ("มีซอสมะเขือเทศไหม", "search_product"),
    ("ขอดูน้ำยาซักผ้าหน่อย", "search_product"),
    ("นำปลาา มีมั้ย", "search_product"),
    ("อยากได้จรวดไปดวงจันทร์", "unknown"),
    ("ทดสอบข้อความมั่ว ๆ xyz123", "unknown"),
]


def _print_row(text, true_intent, kw_intent, bert_pred, bert_score):
    kw_correct = "✓" if kw_intent == true_intent else "✗"
    bert_correct = "✓" if bert_pred == true_intent else "✗"
    print(
        f"{text[:28]:<30}{true_intent:<16}{kw_intent:<14}{kw_correct:<4}"
        f"{bert_pred:<14}{bert_score:<8.2f}{bert_correct}"
    )


def run_comparison():
    """รันเปรียบเทียบทั้ง 2 วิธีกับ TEST_CASES ทั้งหมด พิมพ์ตาราง +
    สรุป accuracy ท้ายสุด คืนค่าเป็น dict สรุปผล เผื่ออยากเอาไปใช้ต่อ"""
    header = (
        f"{'ข้อความ':<30}{'Intent จริง':<16}{'Keyword':<14}{'✓/✗':<4}"
        f"{'BERT':<14}{'Score':<8}{'✓/✗'}"
    )
    print(header)
    print("-" * len(header))

    kw_correct_count = 0
    bert_correct_count = 0

    for text, true_intent in TEST_CASES:
        # ใช้ pipeline เต็มรูปแบบ (intent + entity รวมกัน) ไม่ใช่แค่
        # intent_detector.detect_intent() เดี่ยว ๆ ตามเหตุผลที่อธิบาย
        # ไว้ใน docstring ด้านบน
        kw_intent = process_message(text)["intent"]
        bert_pred, bert_score = bert_intent.detect_intent(text)

        if kw_intent == true_intent:
            kw_correct_count += 1
        if bert_pred == true_intent:
            bert_correct_count += 1

        _print_row(text, true_intent, kw_intent, bert_pred, bert_score)

    total = len(TEST_CASES)
    kw_accuracy = kw_correct_count / total * 100
    bert_accuracy = bert_correct_count / total * 100

    print("-" * len(header))
    print(f"Keyword Matching Accuracy: {kw_correct_count}/{total} ({kw_accuracy:.1f}%)")
    print(f"Sentence-BERT Accuracy:    {bert_correct_count}/{total} ({bert_accuracy:.1f}%)")

    return {
        "total": total,
        "keyword_correct": kw_correct_count,
        "keyword_accuracy": kw_accuracy,
        "bert_correct": bert_correct_count,
        "bert_accuracy": bert_accuracy,
    }


if __name__ == "__main__":
    run_comparison()