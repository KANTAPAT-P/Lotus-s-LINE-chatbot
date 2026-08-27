"""
bert_intent.py
--------------------------------
จับ Intent ด้วย Sentence-BERT (semantic similarity) แทน keyword matching
ใช้เปรียบเทียบกับ intent_detector.py (keyword-based) ตามใบปฏิบัติการ
เรื่อง "เปรียบเทียบ Intent Detection ระหว่าง Keyword Matching กับ
Sentence-BERT" — *** ไม่ได้เอามาใช้ตอบ user จริง *** (flow การตอบจริง
ใน webhook_server.py ยังใช้ text_processor.py/intent_detector.py แบบ
keyword+fuzzy เหมือนเดิมทุกอย่าง ไฟล์นี้มีไว้แค่ทำ log เปรียบเทียบ
คู่ขนานตามที่ใบปฏิบัติการต้องการเท่านั้น)

--------------------------------
วิธีทำงาน: Few-shot Centroid Classifier
--------------------------------
ไม่ได้ train โมเดลใหม่ (ไม่มี dataset ใหญ่พอจะ fine-tune) แต่ใช้วิธี:
1. เตรียมประโยคตัวอย่างของแต่ละ intent ไว้ล่วงหน้า (INTENT_EXAMPLES)
2. เข้ารหัสเป็น embedding ด้วย Sentence-BERT ครั้งเดียวตอนโหลดโมดูล
   แล้วหาค่าเฉลี่ย (centroid) ของแต่ละ intent
3. พอมีข้อความใหม่เข้ามา เข้ารหัสแล้วเทียบ cosine similarity กับ
   centroid ทุก intent เลือกอันที่คะแนนสูงสุด
4. ถ้าคะแนนสูงสุดยังต่ำกว่า UNKNOWN_SCORE_THRESHOLD ให้ถือว่า "unknown"
   (กันกรณีข้อความไม่เกี่ยวกับ intent ไหนเลย แต่ดันมีคะแนนใกล้เคียง
   บาง intent แบบมั่ว ๆ)

ใช้โมเดล paraphrase-multilingual-MiniLM-L12-v2 (จาก sentence-transformers)
เพราะเบา (~118MB) และรองรับหลายภาษารวมถึงไทย เหมาะกับเครื่องที่ไม่มี GPU
"""

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_BERT_AVAILABLE = True
except ImportError:
    # เผื่อเครื่องยังไม่ได้ pip install sentence-transformers จะได้ไม่
    # crash ทั้งระบบ (แต่ฟังก์ชัน detect_intent จะคืน "unavailable" แทน)
    SENTENCE_BERT_AVAILABLE = False

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# คะแนน cosine similarity (0-1) ขั้นต่ำที่ยอมรับว่า "ใช่ intent นี้จริง"
# ต่ำกว่านี้ถือว่า "unknown" ปรับได้ตามผลทดสอบจริง
UNKNOWN_SCORE_THRESHOLD = 0.45

# ตัวอย่างประโยคตัวแทนของแต่ละ intent (few-shot prototypes) — ยิ่งเพิ่ม
# ตัวอย่างที่หลากหลาย ยิ่งช่วยให้ centroid สะท้อนความหมายของ intent
# นั้นได้แม่นขึ้น (ปรับ/เพิ่มได้เรื่อย ๆ ตามผลทดสอบ)
INTENT_EXAMPLES = {
    "greeting": [
        "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดีครับ", "หวัดดีค่ะ",
        "สวัสดีตอนเช้า", "hello", "hi there",
    ],
    "ask_promotion": [
        "มีโปรโมชั่นอะไรบ้าง", "วันนี้มีโปรอะไรลดราคาไหม",
        "อยากรู้เรื่องส่วนลด", "มีของลดราคาไหม",
        "โปรโมชั่นวันนี้มีอะไรบ้าง", "มีดีลอะไรน่าสนใจไหม",
        "ลดกี่เปอร์เซ็นต์", "มีแถมไหม",
    ],
    "search_product": [
        "อยากได้น้ำปลา", "มีซอสมะเขือเทศไหม", "ขอดูน้ำยาซักผ้าหน่อย",
        "หาสินค้าชิ้นนี้", "อยากซื้อของใช้ในบ้าน", "มีของกินขายไหม",
        "ขอดูสินค้าหมวดนี้หน่อย", "มีน้ำยาปรับผ้านุ่มไหม",
    ],
}

_model = None
_intent_centroids = {}


def _load_model():
    """โหลดโมเดล Sentence-BERT ครั้งแรกที่เรียกใช้เท่านั้น (lazy load)
    เพราะโหลดช้าและกินหน่วยความจำ ไม่อยากให้โหลดตอน import โมดูลเฉย ๆ"""
    global _model
    if _model is None and SENTENCE_BERT_AVAILABLE:
        print(f"[bert_intent] กำลังโหลดโมเดล {MODEL_NAME} "
              f"(ครั้งแรกอาจช้าเพราะต้องดาวน์โหลดจาก Hugging Face)...")
        _model = SentenceTransformer(MODEL_NAME)
        print("[bert_intent] โหลดโมเดลสำเร็จ")
    return _model


def _build_centroids():
    """เข้ารหัสตัวอย่างประโยคของแต่ละ intent แล้วหาค่าเฉลี่ย (centroid)
    ทำครั้งเดียวตอนเรียกใช้ครั้งแรก (lazy) แล้วเก็บ cache ไว้"""
    model = _load_model()
    if model is None:
        return {}

    centroids = {}
    for intent, examples in INTENT_EXAMPLES.items():
        embeddings = model.encode(examples)
        centroids[intent] = np.mean(embeddings, axis=0)
    return centroids


def _cosine_similarity(a, b) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
    return float(np.dot(a, b) / denom)


def detect_intent(text: str):
    """
    รับข้อความผู้ใช้ คืนค่าเป็น tuple (intent, similarity_score)
    เพื่อให้เทียบรูปแบบ return value กับ intent_detector.detect_intent()
    ที่คืนแค่ intent เฉย ๆ ได้ง่าย (score เอาไว้โชว์ในตาราง log เปรียบเทียบ)

    คืนค่า ("unavailable", 0.0) ถ้า sentence-transformers ไม่พร้อมใช้งาน
    (ยังไม่ได้ pip install หรือโหลดโมเดลไม่สำเร็จ)
    """
    global _intent_centroids

    if not SENTENCE_BERT_AVAILABLE:
        return "unavailable", 0.0

    if not text or not text.strip():
        return "unknown", 0.0

    if not _intent_centroids:
        _intent_centroids = _build_centroids()

    if not _intent_centroids:
        return "unavailable", 0.0

    model = _load_model()
    text_embedding = model.encode([text])[0]

    best_intent = "unknown"
    best_score = -1.0
    for intent, centroid in _intent_centroids.items():
        score = _cosine_similarity(text_embedding, centroid)
        if score > best_score:
            best_score = score
            best_intent = intent

    if best_score < UNKNOWN_SCORE_THRESHOLD:
        return "unknown", best_score

    return best_intent, best_score


# ----------------------------------
# ทดสอบเดี่ยว ๆ
# ----------------------------------
if __name__ == "__main__":
    if not SENTENCE_BERT_AVAILABLE:
        print("ยังไม่ได้ pip install sentence-transformers — รัน:")
        print("    pip install sentence-transformers")
        print("แล้วลองรันไฟล์นี้ใหม่อีกครั้ง")
    else:
        test_cases = [
            "สวัสดีครับ",
            "วันนี้มีโปรโมชั่นอะไรบ้าง",
            "อยากได้น้ำปลา",
            "มีซอสมะเขือเทศไหม",
            "อยากได้จรวดไปดวงจันทร์",
        ]
        for t in test_cases:
            intent, score = detect_intent(t)
            print(f"{t!r:40} -> intent={intent:<16} score={score:.3f}")