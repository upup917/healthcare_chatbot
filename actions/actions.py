from typing import Any, Text, Dict, List, Optional #ใช้บอกชนิดข้อมูลใน Python เพื่อให้โค้ดอ่านง่าย 
import re #ใช้ regex สำหรับจับ pattern YouTube video id
import requests #ใช้เรียก HTTP API YouTube oEmbed
import psycopg2
from psycopg2.extras import RealDictCursor
from rasa_sdk import Action, Tracker #สำหรับเขียน custom actions ของ Rasa 
from rasa_sdk.executor import CollectingDispatcher

# DB 
PG_HOST = "eilapgsql.in.psu.ac.th"
PG_DB   = "linechatbot"
PG_USER = "pocharapon.d"
PG_PASS = "91}m2T3X-;Pz"
PG_PORT = 5432
def get_db_connection():
    return psycopg2.connect(
        host=PG_HOST, database=PG_DB, user=PG_USER, password=PG_PASS, port=PG_PORT
    )


def fetch_answer_by_question(q: str) -> Optional[str]:  # ค้นหาคำตอบจากตาราง question 
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # ทำ exact ก่อน
        cur.execute("SELECT answer FROM question WHERE question = %s LIMIT 1", (q,))
        row = cur.fetchone()
        if row and row.get("answer"):
            return row["answer"]
        # ถ้าไม่ทำ exact ทำ partial fallback
        cur.execute(
            "SELECT answer FROM question WHERE question ILIKE %s ORDER BY question LIMIT 1",
            (f"%{q}%",),
        )
        row = cur.fetchone()
        if row and row.get("answer"):
            return row["answer"]
        return None
    except Exception as e:
        print("DB error:", e)
        return None
    finally:
        try:
            if cur: cur.close()
            if conn: conn.close()
        except:
            pass

# ตัวช่วยส่งข้อความบน line
def _say(dispatcher: CollectingDispatcher, messages: List[str]):
    for m in messages:
        if m and m.strip():
            dispatcher.utter_message(text=m.strip())
def chunk_text(text: str, limit: int = 900) -> List[str]:
    """แบ่งข้อความยาวเป็นท่อนสั้น ๆ (ป้องกันข้อความพรืดใน LINE)"""
    parts, cur = [], ""
    for line in (text or "").split("\n"):
        if len(cur) + len(line) + 1 > limit:
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts

#youtube oEmbed  
_YT_META_CACHE: Dict[str, Dict[str, str]] = {}
def fetch_youtube_oembed(link: str, timeout: float = 2.5) -> Dict[str, str]: #ดึงข้อมูลคลิป YouTube โดยไม่ต้องใช้ API Key
    if not link:
        return {"title": None, "thumbnail": None}
    # ใช้ cache ก่อนเพื่อลดการยิง HTTP ซ้ำ ๆ
    if link in _YT_META_CACHE:
        return _YT_META_CACHE[link]
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": link, "format": "json"},
            timeout=timeout,
        )
        if r.ok:
            data = r.json()
            meta = {
                "title": data.get("title"),
                "thumbnail": data.get("thumbnail_url"),
            }
            _YT_META_CACHE[link] = meta
            return meta
    except Exception as e:
        print("oEmbed error:", e)

    #fallback ถ้าเรียกไม่ได้
    meta = {"title": None, "thumbnail": None}
    _YT_META_CACHE[link] = meta
    return meta

def truncate(text: str, max_len: int = 60) -> str: #ตัดข้อความชื่อวิดีโอที่ยาวเกินเพื่อให้พอดีการ์ด Flex ใน ine
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len - 1] + "…"

# quick reply 
def _qr(text: str, items: List[Dict[str, str]]) -> Dict:
    return {
        "line_quick_reply": {
            "text": text,
            "items": [
                {"label": it["label"], "text": it["text"]}
                for it in items
            ][:13]  #line จำกัดสูงสุด 13 ปุ่ม
        }
    }

# เมนูหลัก/เมนูย่อย
def send_main_menu(dispatcher: CollectingDispatcher):
    _say(dispatcher, [
        "ลองเลือกหัวข้อที่สนใจด้านล่างได้เลยครับ "
        "กันข้อความไม่ออก"
    ])
    dispatcher.utter_message(json_message=_qr(
        "หัวข้อหลัก",
        [
            {"label": "ข้อมูลโรค", "text": "เมนู ข้อมูลโรค"},
            {"label": "การรักษา", "text": "เมนู การรักษา"},
            {"label": "ดูแลตนเอง", "text": "เมนู ดูแลตนเอง"},
        ]
    ))

def send_disease_menu(dispatcher: CollectingDispatcher):
    _say(dispatcher, [
        "— ข้อมูลโรคมะเร็งเม็ดเลือดขาว —",
        "กันข้อความไม่ออก"
    ])
    dispatcher.utter_message(json_message=_qr(
        "ลองเลือกหัวข้อที่สนใจด้านล่างได้เลยครับ",
        [
            {"label": "โรคคืออะไร",    "text": "โรคมะเร็งเม็ดเลือดขาวคืออะไร"},
            {"label": "อาการของโรค",  "text": "อาการของโรค"},
            {"label": "สาเหตุ/ปัจจัย", "text": "สาเหตุและปัจจัยเสี่ยง"},
        ]
    ))

def send_treatment_menu(dispatcher: CollectingDispatcher):
    _say(dispatcher, [
        "— การรักษา —",
        "กันข้อความไม่ออก"
    ])
    dispatcher.utter_message(json_message=_qr(
        "หากสงสัยจุดไหน ผมช่วยอธิบายได้ครับ",
        [
            {"label": "คีโมคืออะไร",  "text": "เคมีบำบัดคืออะไร"},
            {"label": "ผลข้างเคียง", "text": "ผลข้างเคียง"},
            {"label": "ข้อควรปฏิบัติ", "text": "ข้อควรปฏิบัติระหว่างรักษา"},
        ]
    ))

def send_selfcare_menu(dispatcher: CollectingDispatcher):
    _say(dispatcher, [
        "— การดูแลตนเอง —",
        "กันข้อความไม่ออก"
    ])
    dispatcher.utter_message(json_message=_qr(
        "ผมช่วยแนะนำได้ครับ เลือกหัวข้อที่สนใจเลยครับ",
        [
            {"label": "จัดการอารมณ์",    "text": "การจัดการอารมณ์"},
            {"label": "ระหว่างพักฟื้น",  "text": "การดูแลระหว่างพักฟื้น"},
            {"label": "อาหาร",           "text": "การรับประทานอาหาร"},
        ]
    ))

def send_faq_menu(dispatcher: CollectingDispatcher):
    _say(dispatcher, [
        " คำถามที่พบบ่อย ",
        "กันข้อความไม่ออก"
    ])
    dispatcher.utter_message(json_message=_qr(
        "เลือกคำถามที่ต้องการทราบได้เลยครับ ",
        [
            {"label": "โรคนี้คืออะไร",       "text": "โรคมะเร็งเม็ดเลือดขาวคืออะไร"},
            {"label": "อาหารที่กินได้",      "text": "การรับประทานอาหาร"},
            {"label": "ดูแลระหว่างเป็นโรค",  "text": "การดูแลระหว่างพักฟื้น"},
        ]
    ))
    
# ตอบจาก DB 
class ActionGetAnswer(Action): 
    def name(self) -> Text:
        return "action_get_answer"

    def run(self,dispatcher: CollectingDispatcher, #ดู intent ล่าสุดจาก Tracker
            tracker: Tracker,domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # mapping intent question ในตาราง question
        question_mapping = {
            "ask_disease_what":           "โรคมะเร็งเม็ดเลือดขาวคืออะไร",
            "ask_disease_symptoms":       "อาการของโรค",
            "ask_disease_cause":          "สาเหตุและปัจจัยเสี่ยง",
            "ask_treatment_chemo_what":   "เคมีบำบัดคืออะไร",
            "ask_treatment_side_effects": "ผลข้างเคียง",
            "ask_selfcare_emotion":       "การจัดการอารมณ์",
            "ask_selfcare_rest":          "การดูแลระหว่างพักฟื้น",
            "ask_selfcare_diet":          "การรับประทานอาหาร",
            "ask_contact_info":           "ข้อมูลติดต่อ",
            "ask_treatment_dos_donts":    "ข้อควรปฏิบัติระหว่างรักษา",
        }

        intent_name = tracker.latest_message.get("intent", {}).get("name")
        q = question_mapping.get(intent_name)

        if not q:
            _say(dispatcher, [
                "ลองเลือกหัวข้อจากเมนูด้านล่างได้เลยครับ"
            ])
            send_main_menu(dispatcher)
            return []

        # ตอบคำถาม
        ans = fetch_answer_by_question(q)
        if ans:
            for part in chunk_text(ans): #ส่งเป็นข้อความหลายท่อน 
                dispatcher.utter_message(text=part)
        else:
            _say(dispatcher, [
                "ขออภัยครับ ตอนนี้ยังไม่มีข้อมูลในหัวข้อนี้",
                "ลองเลือกหัวข้ออื่นจากเมนูได้เลยครับ"
            ])
            send_main_menu(dispatcher)
            return []

        # เสนอหัวข้อที่เกี่ยวข้องในหมวดเดียวกันต่อ
        disease   = ["ask_disease_what", "ask_disease_symptoms", "ask_disease_cause"]
        treatment = ["ask_treatment_chemo_what", "ask_treatment_side_effects", "ask_treatment_dos_donts"]
        selfcare  = ["ask_selfcare_emotion", "ask_selfcare_rest", "ask_selfcare_diet"]

        if intent_name in disease:
            _say(dispatcher, [
                "ต้องการดูหัวข้ออื่นใน ‘ข้อมูลโรค’ ต่อไหมครับ",
            ])
            options = []
            if intent_name != "ask_disease_what":
                options.append({"label": "โรคคืออะไร", "text": "โรคมะเร็งเม็ดเลือดขาวคืออะไร"})
            if intent_name != "ask_disease_symptoms":
                options.append({"label": "อาการของโรค", "text": "อาการของโรค"})
            if intent_name != "ask_disease_cause":
                options.append({"label": "สาเหตุของโรค", "text": "สาเหตุและปัจจัยเสี่ยง"})
            if options:
                dispatcher.utter_message(json_message=_qr("สนใจข้อมูลไหนต่อสามารถเลือกได้เลยครับ", options))

        elif intent_name in treatment:
            _say(dispatcher, [
                "สนใจดูหัวข้ออื่นเกี่ยวกับ ‘การรักษา’ ต่อไหมครับ ",
            ])
            options = []
            if intent_name != "ask_treatment_chemo_what":
                options.append({"label": "คีโมคืออะไร", "text": "เคมีบำบัดคืออะไร"})
            if intent_name != "ask_treatment_side_effects":
                options.append({"label": "ผลข้างเคียง", "text": "ผลข้างเคียง"})
            if intent_name != "ask_treatment_dos_donts":
                options.append({"label": "ข้อควรปฏิบัติ", "text": "ข้อควรปฏิบัติระหว่างรักษา"})
            if options:
                dispatcher.utter_message(json_message=_qr("อยากรู้ข้อมูลไหนเป็นพิเศษสามารถดูเพิ่มเติมได้เลยครับ", options))

        elif intent_name in selfcare:
            _say(dispatcher, [
                "อยากให้ผมแนะนำการ ‘ดูแลตนเอง’ หัวข้ออื่นเพิ่มเติมไหมครับ",
            ])
            options = []
            if intent_name != "ask_selfcare_emotion":
                options.append({"label": "จัดการอารมณ์", "text": "การจัดการอารมณ์"})
            if intent_name != "ask_selfcare_rest":
                options.append({"label": "ระหว่างพักฟื้น", "text": "การดูแลระหว่างพักฟื้น"})
            if intent_name != "ask_selfcare_diet":
                options.append({"label": "อาหาร", "text": "การรับประทานอาหาร"})
            if options:
                dispatcher.utter_message(json_message=_qr("เลือกหัวข้อที่สนใจต่อได้เลยครับ", options))
        else:
            _say(dispatcher, [
                "ถ้าต้องการดูหัวข้ออื่นๆเพิ่มเติมสามารถกลับไปที่เมนูหลักได้เลยครับ"
            ])
            send_main_menu(dispatcher)

        return []

#แสดงวิดีโอ YouTube 
class ActionGetLearningResources(Action):
    def name(self) -> Text:
        return "action_get_learning_resources"

    def run(self, dispatcher, tracker, domain):
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor) 
            cur.execute("SELECT link FROM youtubelink ORDER BY id LIMIT 5") # ดึง link จากตาราง youtubelink
            rows = cur.fetchall()

            if not rows:
                dispatcher.utter_message(text="ยังไม่มีวิดีโอเพิ่มเติมในตอนนี้ครับ")
                return []
            videos = [row["link"] for row in rows]
            flex_contents = []
            for i, link in enumerate(videos):
                #ดึง metadata จาก oEmbed
                meta = fetch_youtube_oembed(link)
                title = meta.get("title") or f"วิดีโอ #{i+1}"
                title = truncate(title, 70)

                #หา thumbnail 
                thumb = meta.get("thumbnail")
                if not thumb:
                    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", link)
                    video_id = match.group(1) if match else None
                    thumb = f"https://img.youtube.com/vi/{video_id}/0.jpg" if video_id else "https://i.imgur.com/placeholder.png"

                #สร้าง bubble ด้วย title จริง
                flex_contents.append({
                    "type": "bubble",
                    "hero": {
                        "type": "image",
                        "url": thumb,
                        "size": "full",
                        "aspectRatio": "16:9",
                        "aspectMode": "cover",
                        "action": {"type": "uri", "uri": link}
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True},
                            {"type": "text", "text": "กดดูวิดีโอบน YouTube", "size": "sm", "color": "#888888", "wrap": True}
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#365486",
                                "action": {"type": "uri", "label": "ดูวิดีโอ", "uri": link}
                            }
                        ]
                    }
                })

            flex_message = {
                "line_flex": {
                    "altText": "แหล่งการเรียนรู้เพิ่มเติมจาก YouTube",
                    "contents": {
                        "type": "carousel",
                        "contents": flex_contents
                    }
                }
            }
            dispatcher.utter_message(json_message=flex_message) #ส่งออก

        except Exception as e:
            print("DB error:", e)
            dispatcher.utter_message(text="ขออภัยไม่สามารถดึงวิดีโอได้ในตอนนี้")
        finally:
            if cur: cur.close()
            if conn: conn.close()
        return []

# Actions เมนู
class ActionSendMainMenu(Action):
    def name(self) -> Text:
        return "action_send_main_menu"
    def run(self, dispatcher, tracker, domain):
        send_main_menu(dispatcher);  return []

class ActionSendDiseaseMenu(Action):
    def name(self) -> Text:
        return "action_send_disease_menu"
    def run(self, dispatcher, tracker, domain):
        send_disease_menu(dispatcher);  return []

class ActionSendTreatmentMenu(Action):
    def name(self) -> Text:
        return "action_send_treatment_menu"
    def run(self, dispatcher, tracker, domain):
        send_treatment_menu(dispatcher);  return []

class ActionSendSelfcareMenu(Action):
    def name(self) -> Text:
        return "action_send_selfcare_menu"
    def run(self, dispatcher, tracker, domain):
        send_selfcare_menu(dispatcher);  return []

class ActionSendFaqMenu(Action):
    def name(self) -> Text:
        return "action_send_faq_menu"
    def run(self, dispatcher, tracker, domain):
        send_faq_menu(dispatcher);  return []