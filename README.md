# Lotus's LINE Chatbot

LINE Chatbot สำหรับค้นหาสินค้าและโปรโมชั่นจาก Lotus's แบบผสมผสาน — ใช้ข้อมูลที่ scrape เก็บไว้ล่วงหน้า (833 หมวดหมู่) เป็นหลัก และ fallback ไปค้นหาสดจากเว็บไซต์จริงเมื่อหาไม่เจอในข้อมูล local (เช่น ค้นหาด้วยชื่อแบรนด์)

> โปรเจกต์นี้เป็นงาน Assignment เดี่ยว **ไม่ใช่งานของ Lotus's จริง** ใช้เพื่อการศึกษาเท่านั้น

---

## ✨ Features

- **NLP Intent + Entity Detection** — จับความต้องการผู้ใช้ (หาสินค้า/ถามโปรโมชั่น/ทักทาย) และดึงชื่อสินค้า/หมวดหมู่จากข้อความ ด้วย Keyword Matching + Fuzzy Matching (ทนคำพิมพ์ผิด)
- **Hybrid Search** — ค้นหาจากข้อมูล local ก่อน (เร็ว ไม่ผ่าน network) ถ้าไม่เจอ fallback ไปค้นสดจากเว็บ Lotus's จริง (เช่น ค้นชื่อแบรนด์ที่ไม่มีในหมวดหมู่)
- **Top 5 Random Selection** — สุ่มเลือกสินค้า 5 ชิ้นจากผลลัพธ์ พร้อมกันไม่ให้สินค้าชุดเดิมโผล่ซ้ำถี่เกินไป และให้ความสำคัญกับสินค้าที่มีโปรโมชั่นก่อนเมื่อถามเรื่องโปร
- **Promotion Parser** — จำแนกโปรโมชั่นอัตโนมัติ 4 แบบ (ลด%, ซื้อ X ราคาพิเศษ, ซื้อ X แถม X, ซื้อครบ X ลดทันที X) จาก field ที่มีอยู่แล้วในข้อมูลสินค้า ไม่ต้อง scrape หน้าโปรโมชั่นแยก
- **Flex Message Carousel** — การ์ดสินค้าสวยงาม พร้อม badge สีตามประเภทโปร, ราคาขีดฆ่าเมื่อมีส่วนลด, ลิงก์ไปหน้าสินค้าจริง
- **Quick Reply / Postback** — ปุ่ม "ขอดูโปรโมชั่น" / "ถูกสุด" / "แพงสุด" ให้กดต่อได้เลยหลังเห็นผลค้นหา
- **Multi-step Reply** — ตอบเป็นหลายข้อความต่อเนื่องกัน (กำลังค้นหา → สรุปจำนวน → การ์ดสินค้า) ให้ความรู้สึกเป็นขั้นตอน
- **BERT vs Keyword Comparison** — เปรียบเทียบความแม่นยำ Intent Detection ระหว่าง Keyword Matching กับ Sentence-BERT (สำหรับส่วนวิเคราะห์ในรายงาน ไม่กระทบการตอบจริง)

---

## 🏗️ โครงสร้างโปรเจกต์

```
Lotus_line_chatbot/
├── AI_text_processing/          # ประมวลผลข้อความผู้ใช้ (NLP)
│   ├── intent_detector.py       #   จับ intent ด้วย keyword matching
│   ├── entity_extractor.py      #   จับชื่อสินค้า/หมวดหมู่ (exact + fuzzy)
│   ├── text_processor.py        #   entry point รวม intent+entity
│   ├── bert_intent.py           #   จับ intent ด้วย Sentence-BERT (สำหรับเปรียบเทียบ)
│   └── compare_intent.py        #   สคริปต์เปรียบเทียบ Keyword vs BERT
│
├── Function/                    # Business logic หลัก
│   ├── lotus_searching.py       #   ค้นหาสินค้าจาก data/all_product/
│   ├── top5_selector.py         #   สุ่มเลือก/เรียง 5 อันดับสินค้า
│   ├── promotion_parser.py      #   จำแนกประเภทโปรโมชั่น
│   ├── product_view_model.py    #   แปลงสินค้าดิบ -> view model กลาง
│   └── flex_builder.py          #   view model -> Flex Message
│
├── scraping/                    # เก็บข้อมูลสินค้า
│   ├── get_categories.py        #   ดึง category tree -> categories_flat.json
│   ├── scrap_all_product.py     #   scrape สินค้าทุกหมวด (batch, resumable)
│   └── scrap_current_product.py #   ค้นหาสินค้าสด (ใช้ตอน fallback)
│
├── webhook_server/
│   └── webhook_server.py        # จุดรับ-ส่งข้อความ LINE, รวม pipeline ทั้งหมด
│
├── data/
│   ├── categories/categories_flat.json   # 833 leaf categories
│   └── all_product/                      # สินค้าทุกหมวด (~255 MB)
│
├── tests/
│   └── test_full_pipeline.py    # ทดสอบ pipeline เต็มรูปแบบ
│
├── .env                          # CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN
├── config.py
└── requirements.txt
```

---

## 🔄 Pipeline การทำงาน

```
user พิมพ์ข้อความ
    │
    ▼
text_processor.py (intent + entity จาก local category vocabulary)
    │
    ├── entity เจอ (เช่น "น้ำปลา")
    │     → lotus_searching.py เปิด data/all_product/<id>_<slug>.json
    │     → top5_selector.get_top5_with_promotion()
    │           (ให้ความสำคัญสินค้ามีโปรก่อน ถ้า intent=ask_promotion)
    │
    └── entity ไม่เจอ (เช่น "เลย์", ชื่อแบรนด์) หรือ local error
          → scrap_current_product.py ค้นหาสดจาก Lotus's
          → top5_selector.get_top5_with_promotion() เช่นกัน
    │
    ▼ (ทั้ง 2 เส้นทางมาบรรจบที่นี่)
product_view_model.build_view_models()   # แปลงเป็น view model กลาง
    │
    ▼
flex_builder.build_flex_reply()          # สร้าง Flex Carousel
    │
    ▼
ส่งเข้า LINE (พร้อม Quick Reply แนบท้าย)
```

**เมื่อ user กด Quick Reply** (ขอดูโปรโมชั่น / ถูกสุด / แพงสุด) → ส่งเป็น **Postback Event** แยกต่างหาก → `handle_postback()` ค้นหาสินค้าใหม่จาก key ที่ฝังไว้ในปุ่ม (category_id หรือ `live:<คำค้น>`) แล้วกรอง/เรียงตามปุ่มที่กด

---

## ⚙️ วิธีติดตั้งและรัน

### 1. ติดตั้ง dependencies
```bash
pip install -r requirements.txt --break-system-packages
```
ไลบรารีหลักที่ใช้: `flask`, `line-bot-sdk`, `python-dotenv`, `requests`, `rapidfuzz`, `sentence-transformers` (สำหรับ BERT comparison เท่านั้น)

### 2. ตั้งค่า `.env`
```env
CHANNEL_SECRET=your_line_channel_secret
CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
```

### 3. เตรียมข้อมูลสินค้า (รันครั้งเดียว ใช้เวลานาน)
```bash
cd scraping
python get_categories.py       # ดึง category tree -> ได้ categories_flat.json (833 หมวด)
python scrap_all_product.py    # scrape สินค้าทุกหมวด (resumable, รันซ้ำได้ถ้าหยุดกลางทาง)
```

### 4. รัน webhook server
```bash
cd webhook_server
python webhook_server.py
```

### 5. เปิด tunnel เชื่อมกับ LINE (สำหรับทดสอบ)
```bash
cloudflared tunnel --url http://localhost:5000
```
เอา URL ที่ได้ไปตั้งค่าใน LINE Developers Console > Messaging API > Webhook URL

> ⚠️ URL จาก `cloudflared tunnel` แบบ quick tunnel จะเปลี่ยนทุกครั้งที่รันใหม่ ต้องอัปเดต Webhook URL ทุกรอบ ถ้าต้องการ URL ถาวรควรพิจารณา deploy จริง (Railway, Render, VPS)

### 6. (ทางเลือก) เปิดใช้ Auto-response ใน LINE OA Manager
ตั้งข้อความอัตโนมัติ เช่น "⚙️ระบบกำลังประมวลผลข้อความผู้ใช้⚙️" ให้ตอบทันทีโดยไม่ผ่าน webhook (ช่วยให้ user รู้สึกว่าระบบตอบสนองเร็ว ระหว่างรอ webhook ประมวลผลจริง)

---

## 🧪 การทดสอบ

แต่ละไฟล์มี self-test ในตัว รันตรงๆ ได้เลย:
```bash
python AI_text_processing/text_processor.py
python AI_text_processing/entity_extractor.py
python AI_text_processing/compare_intent.py     # เปรียบเทียบ Keyword vs BERT
python Function/top5_selector.py
python Function/promotion_parser.py
python Function/flex_builder.py
```

ทดสอบ pipeline เต็มรูปแบบด้วยข้อมูลจริง (สุ่มเทสจากหมวดหมู่จริง + edge case ที่เคยเจอบั๊ก):
```bash
python tests/test_full_pipeline.py
```

---

## 📝 บันทึกการพัฒนา: ปัญหาที่พบและวิธีแก้ไข

ระหว่างพัฒนาเจอบั๊กหลายจุดที่น่าสนใจ (ส่วนใหญ่เกี่ยวกับ fuzzy matching และโครงสร้างข้อมูลจริงที่ไม่สม่ำเสมอ) สรุปไว้เป็นบันทึกการเรียนรู้:

| # | ปัญหา | สาเหตุ | วิธีแก้ |
|---|---|---|---|
| 1 | Exact match เจอชื่อสั้น (เช่น "ปลา") ทั้งที่ user พิมพ์ผิดจนพลาดชื่อที่ถูกต้อง (เช่น "น้ำปลา") | จับคู่ substring แบบตรงตัวอย่างเดียว ไม่ทนคำพิมพ์ผิด | เพิ่ม "Superset Detection" — ถ้า exact match ได้ชื่อสั้น ให้ลอง fuzzy อัปเกรดไปชื่อยาวที่เกี่ยวข้องก่อนสรุปผล |
| 2 | คำว่า "โปรโมชั่น" เดี่ยวๆ ไป fuzzy match ผิดกับหมวดที่ชื่อมีคำนี้ซ้อนอยู่ (เช่น "โปรตีนขายดีและโปรโมชั่น") | `fuzz.partial_ratio` ให้คะแนนเต็ม 100 เสมอถ้าข้อความสั้นเป็น substring ของข้อความยาว ไม่สนบริบท | ตัดคำที่เป็น intent keyword ออกจากข้อความก่อนค้นหา entity ถ้าตัดแล้วไม่เหลืออะไร ข้ามการหา entity ไปเลย |
| 3 | "น้ำปลา" พิมพ์ตรงเป๊ะ กลับถูกอัปเกรดผิดไปเป็นหมวดอื่นที่ไม่เกี่ยวข้อง | ปัญหาเดียวกับ #2 แต่เกิดใน "ขั้นอัปเกรด" ที่ยังไม่ได้แก้ | ถ้าข้อความตรงกับชื่อ category เป๊ะทั้งประโยคอยู่แล้ว ข้ามการลองอัปเกรดไปเลย (มั่นใจสูงสุดแล้ว) |
| 4 | Threshold ของ fallback fuzzy (ค้นทั้ง 833 หมวด) ตั้งไว้หลวมกว่า threshold ของการอัปเกรด ทั้งที่ควรเข้มกว่า | Fallback ค้นแบบไม่มีตัวกรองช่วยเลย เสี่ยง false positive สูงกว่า (เช่น "ถั่ว" กับคำมั่วที่มี "มั่ว" ปน) | ปรับ threshold ของ fallback ให้เท่ากับ/เข้มกว่า threshold การอัปเกรด |
| 5 | ข้อความที่มีตัวอักษรซ้ำจากการพิมพ์เน้นเสียง (เช่น "โปรโมชั่นนนนนน") หลุดไป fallback ค้นสดด้วยคำมั่วๆ | ตัด intent keyword ออกแล้วเหลือแต่ตัวอักษรซ้ำ ซึ่งไม่ว่างเปล่าทางเทคนิคแต่ก็ไม่มีความหมาย | เพิ่มการเช็คว่าข้อความที่เหลือเป็น "ตัวอักษรเดียวกันซ้ำล้วนๆ" ไหม ถ้าใช่ถือเหมือนว่างเปล่า |
| 6 | ลิงก์สินค้าพาไปหน้าผิดสำหรับสินค้าบางชิ้น | ใช้ field `sku` ประกอบลิงก์ แต่จริงๆ ต้องใช้ `urlKey` (บางชิ้น `sku`/`urlKey` เป็นตัวเลขเดียวกันบังเอิญ แต่บางชิ้น `urlKey` เป็น slug ข้อความ) | เปลี่ยนไปใช้ `urlKey` เป็นหลักเสมอ |
| 7 | โปรโมชั่นแบบ "ซื้อครบ X ลดทันที X" (หลายระดับ) แสดงผล badge ยาวเป็นพรืดพร้อม `<br>` ดิบ | โครงสร้างข้อมูลของ ruleType นี้ (`bxtpgd`) ต่างจาก 2 แบบก่อนหน้า ข้อความเต็มอยู่ที่ `promotions[0].offerText` โดยตรง ไม่ได้ซ้อนใน `autoBadge.imagePromotion` เหมือนแบบอื่น | เพิ่ม parser เฉพาะสำหรับ `bxtpgd` แยก parse เป็น list ของ (ยอดซื้อ, ส่วนลด) แล้วโชว์แค่ระดับแรก+ส่วนลดสูงสุดใน badge |
| 8 | Lotus's search engine เองบางครั้งคืนสินค้าที่ไม่เกี่ยวข้องกับคำค้นเลย (เช่น พิมพ์ตัวอักษรมั่วๆ แล้วได้ตู้เย็น/ปลั๊กไฟ) | พฤติกรรมของ search engine ฝั่ง Lotus's เอง ควบคุมไม่ได้ และไม่คงเส้นคงวา (บางคำมั่วตอบ "ไม่เจอ" ถูกต้อง บางคำกลับคืนผลมั่วมา) | ลองเพิ่ม relevance check (fuzzy compare คำค้นกับชื่อสินค้า) แต่พบว่าเข้มงวดเกินไปจนทำให้ query ปกติ (เช่น "cheetos") ก็ถูกกรองผิดไปด้วย **จึง rollback ออก** และเปลี่ยนไปแจ้ง user แทนว่ากำลังค้นหาจากเว็บไซต์โดยตรง |

---

## ⚠️ ข้อจำกัดที่ทราบอยู่แล้ว (Known Limitations)

- **ประวัติกันสินค้าซ้ำ** (`top5_selector.py`) เก็บอยู่ใน memory ของ process เท่านั้น หาย ไปเมื่อ restart server และไม่ share กันถ้ารันหลาย worker process พร้อมกัน
- **Lotus's search engine เอง** อาจคืนผลลัพธ์ไม่เกี่ยวข้องกับคำค้นในบางกรณี (ดูบันทึกข้อ 8) เป็นข้อจำกัดที่ยอมรับแล้วเนื่องจากพยายามแก้แล้วแต่ทำให้ผลลัพธ์แย่กว่าเดิม
- **Entity vocabulary ครอบคลุมแค่ leaf category** (833 หมวดย่อยสุดท้าย) ไม่ครอบคลุมหมวดหมู่ใหญ่ (level 1/2) เช่น คำถามกว้างๆ อย่าง "น้ำอัดลม" อาจไม่ match กับ local data โดยตรง แต่ก็ยัง fallback ไปค้นสดได้ผลลัพธ์ที่ถูกต้องอยู่ดี
- **`cloudflared tunnel` แบบ quick tunnel** ให้ URL ชั่วคราวที่เปลี่ยนทุกครั้งที่รันใหม่ ไม่เหมาะกับการใช้งานระยะยาว

---

## 📊 เกณฑ์การประเมิน (Rubric Mapping)

| ด้านการประเมิน | ไฟล์ที่เกี่ยวข้อง |
|---|---|
| Web Scraping & Data Pipeline | `scraping/get_categories.py`, `scraping/scrap_all_product.py` (resumable, error handling, delay ระหว่าง request) |
| NLP Command Processing | `AI_text_processing/` ทั้งโฟลเดอร์ (keyword+fuzzy, ทนคำพิมพ์ผิด, `compare_intent.py` สำหรับเทียบกับ BERT) |
| Top 5 Carousel Logic & Randomization | `Function/top5_selector.py` (สุ่ม + กันซ้ำ + ให้ความสำคัญโปร) |
| LINE Interface & Chat UX | `webhook_server/webhook_server.py` (Flex Message, Quick Reply, multi-step reply) |
| Code Quality & Performance | Error handling ทุกจุด, timeout guard, modular design แยกแต่ละหน้าที่ชัดเจน, มี self-test ในทุกไฟล์ |