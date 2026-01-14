import subprocess
import sys

# تثبيت المكتبات تلقائيًا (للتشغيل الأول فقط)
def install_packages():
    packages = ['flask', 'python-telegram-bot', 'requests', 'python-dotenv']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"📦 تثبيت: {package}")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

install_packages()

# =============== الاستيرادات بعد التثبيت ===============
import os
import json
import time
import threading
import asyncio
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import requests

# =============== الإعدادات ===============
PORT = int(os.environ.get("PORT", 10000))
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAFZNuyv5Ua17hnJG4XHdB5JuRwZVCwJPCM")
CHAT_ID = int(os.getenv("CHAT_ID", "6968612778"))  # الخاص
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003218943676"))  # القناة
SELF_CHAT_ID = 6968612778  # ← نفس البوت (لإرسال الميديا إليه لاستقباله في n8n)

VIDEOS_DIR = "videos"
SEND_INTERVAL = 300  # 5 دقائق
STATE_FILE = "state.json"
LOG_FILE = "bot.log"

# =============== التهيئة ===============
os.makedirs(VIDEOS_DIR, exist_ok=True)

# =============== اللوغينغ ===============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============== Flask App ===============
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "service": "Telegram Video Relay Bot",
        "webhook_ready": True,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "uptime": time.time() - START_TIME})

# 🔥 Webhook لـ n8n — هذا هو المفتاح!
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """يُفعّل عند وصول أي رسالة/فيديو إلى البوت (مثل من القناة أو من إرسال ذاتي)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data"}), 400

        # استخراج البيانات الأساسية
        message = data.get("message", {})
        video = message.get("video", {})
        caption = message.get("caption", "")
        chat = message.get("chat", {})
        message_id = message.get("message_id")
        date = message.get("date")

        # إذا كان فيه فيديو
        if video:
            file_id = video.get("file_id")
            file_unique_id = video.get("file_unique_id")
            width = video.get("width")
            height = video.get("height")
            duration = video.get("duration")
            file_size = video.get("file_size")

            # ⚡ طلب رابط الملف الفعلي (اختياري — مفيد لـ n8n)
            file_url = None
            try:
                get_file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
                resp = requests.get(get_file_url).json()
                if resp.get("ok"):
                    file_path = resp["result"]["file_path"]
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            except Exception as e:
                logger.warning(f"⚠️ فشل جلب file_url: {e}")

            # ✅ إرجاع كل البيانات المهمة لـ n8n
            payload = {
                "type": "video",
                "file_id": file_id,
                "file_unique_id": file_unique_id,
                "caption": caption,
                "chat_id": chat.get("id"),
                "chat_type": chat.get("type"),
                "chat_title": chat.get("title") or chat.get("username"),
                "message_id": message_id,
                "date": datetime.fromtimestamp(date).isoformat() if date else None,
                "video": {
                    "width": width,
                    "height": height,
                    "duration": duration,
                    "file_size": file_size,
                    "file_url": file_url  # ← مهم جدًا لاستخدامه في Social Media Nodes
                },
                "raw_update": data  # ← لمن تحتاج الـ full payload
            }

            logger.info(f"📤 Webhook triggered | Video: {file_id[:10]}... | Caption: {caption[:30]}")
            return jsonify(payload), 200

        # إذا لم يكن فيديو (مثلاً نص أو صورة)
        else:
            payload = {
                "type": "other",
                "chat_id": chat.get("id"),
                "message_id": message_id,
                "text": message.get("text", ""),
                "caption": caption,
                "date": datetime.fromtimestamp(date).isoformat() if date else None,
                "raw_update": data
            }
            logger.info(f"📤 Webhook (non-video): {payload['text'][:50]}...")
            return jsonify(payload), 200

    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# =============== دوال المساعدة ===============
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ فشل تحميل الحالة: {e}")
    return {"last_sent_index": -1, "videos_list": [], "last_sent_time": None}

def save_state(state):
    try:
        state["updated_at"] = datetime.now().isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ فشل حفظ الحالة: {e}")

def scan_videos():
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'}
    videos = []
    try:
        for filename in os.listdir(VIDEOS_DIR):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                filepath = os.path.join(VIDEOS_DIR, filename)
                if os.path.isfile(filepath):
                    caption = os.path.splitext(filename)[0]  # بدون امتداد
                    videos.append({
                        "path": filepath,
                        "filename": filename,
                        "caption": caption[:1000],
                        "size": os.path.getsize(filepath)
                    })
        videos.sort(key=lambda x: x["filename"])
        total_mb = sum(v["size"] for v in videos) / (1024 * 1024)
        logger.info(f"📁 {len(videos)} فيديو جاهز ({total_mb:.1f} MB)")
        return videos
    except Exception as e:
        logger.error(f"❌ خطأ في فحص الفيديوهات: {e}")
        return []

# =============== إرسال الفيديو (إلى الخاص ← القناة ← البوت نفسه) ===============
async def send_video_cycle(bot, video):
    try:
        # 1️⃣ إرسال إلى الخاص
        logger.info(f"📤 [1/3] إرسال إلى الخاص: {video['filename']}")
        with open(video["path"], "rb") as f:
            await bot.send_video(
                chat_id=CHAT_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True
            )
        await asyncio.sleep(1)

        # 2️⃣ إرسال إلى القناة
        logger.info(f"📤 [2/3] إرسال إلى القناة: {video['filename']}")
        with open(video["path"], "rb") as f:
            msg = await bot.send_video(
                chat_id=CHANNEL_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True
            )
        file_id = msg.video.file_id
        logger.info(f"✅ حصلنا على file_id: {file_id[:15]}...")

        await asyncio.sleep(1)

        # 3️⃣ ⭐ إرسال إلى البوت نفسه (لتفعيل webhook في n8n)
        logger.info("🤖 [3/3] إرسال إلى البوت نفسه (لـ n8n webhook)")
        await bot.send_video(
            chat_id=SELF_CHAT_ID,
            video=file_id,  # ← استخدام file_id (أفضل من إعادة رفع الملف)
            caption=video["caption"],
            supports_streaming=True
        )
        logger.info("✅ أُرسل إلى البوت بنجاح — سيتم تفعيل /webhook الآن!")

        return True

    except Exception as e:
        logger.error(f"❌ فشل دورة الإرسال: {e}")
        return False

# =============== الحلقة الدورية ===============
async def video_sender_loop():
    logger.info("🔁 بدء حلقة إرسال الفيديوهات...")
    bot = Bot(token=BOT_TOKEN)

    while True:
        try:
            videos = scan_videos()
            if not videos:
                logger.warning("📭 لا توجد فيديوهات — انتظر 60 ثانية")
                await asyncio.sleep(60)
                continue

            state = load_state()
            current_list = [v["filename"] for v in videos]
            if state["videos_list"] != current_list:
                logger.info("🔄 تحديث قائمة الفيديوهات")
                state.update({"videos_list": current_list, "last_sent_index": -1})

            next_idx = (state["last_sent_index"] + 1) % len(videos)
            video = videos[next_idx]

            logger.info(f"🎬 إرسال: {video['filename']} ({next_idx + 1}/{len(videos)})")
            if await send_video_cycle(bot, video):
                state["last_sent_index"] = next_idx
                state["last_sent_time"] = datetime.now().isoformat()
                save_state(state)

            logger.info(f"⏳ الانتظار {SEND_INTERVAL} ثانية...")
            await asyncio.sleep(SEND_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.exception(f"💥 خطأ في الحلقة: {e}")
            await asyncio.sleep(30)

# =============== Keep-Alive (لـ Render) ===============
def keep_alive():
    while True:
        try:
            requests.get(f"http://localhost:{PORT}/health", timeout=5)
        except:
            pass
        time.sleep(250)

# =============== التشغيل ===============
START_TIME = time.time()

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Telegram Video Relay Bot — جاهز لـ n8n")
    print(f"   🌐 Webhook: POST /webhook")
    print(f"   📁 مجلد الفيديوهات: {os.path.abspath(VIDEOS_DIR)}")
    print(f"   🕒 كل {SEND_INTERVAL} ثانية")
    print(f"   📞 Chat ID: {CHAT_ID}")
    print(f"   📢 Channel ID: {CHANNEL_ID}")
    print(f"   🤖 Self ID (لـ n8n): {SELF_CHAT_ID}")
    print("=" * 60)

    # تشغيل Flask في thread منفصل
    flask_thread = threading.Thread(target=lambda: app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    ), daemon=True)
    flask_thread.start()

    # تشغيل keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()

    # تشغيل الحلقة الدورية (async)
    try:
        asyncio.run(video_sender_loop())
    except KeyboardInterrupt:
        logger.info("👋 تم الإيقاف يدويًا")
    except Exception as e:
        logger.critical(f"🔥 خطأ فادح: {e}")
