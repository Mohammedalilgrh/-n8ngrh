import subprocess
import sys

# تثبيت المكتبات تلقائيًا
def install_packages():
    # python-telegram-bot import name is "telegram"
    packages = [
        ("flask", "flask"),
        ("python-telegram-bot", "telegram"),
        ("requests", "requests"),
    ]
    for pip_name, import_name in packages:
        try:
            __import__(import_name)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

install_packages()

# ثم استمر في باقي imports
from flask import Flask, jsonify
import os
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot, error as telegram_error
from telegram.ext import Application, MessageHandler, filters
import threading
import requests

PORT = int(os.environ.get("PORT", 10000))  # تعريف PORT هنا

# ================== LOGGING ==================
LOG_FILE = "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== FLASK APP ==================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "message": "Telegram Video Bot is active",
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

# ================== CONFIG ==================
# IMPORTANT: set tokens in env vars, don't hardcode them
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAFZNuyv5Ua17hnJG4XHdB5JuRwZVCwJPCM")        # Bot1 token (sender)
BOT2_TOKEN = os.getenv("BOT2_TOKEN", "7970489926:AAGnzN-CGai1kpFs1gGOmykqPE4y7Rv0Bvk")      # Bot2 token (listener for n8n)

CHAT_ID = os.getenv("CHAT_ID", "6968612778")  # receiver (private/group)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003218943676"))  # channel

# Time between each video send (seconds)
# Change here OR set env var SEND_INTERVAL (example: 600 for 10 minutes)
SEND_INTERVAL = int(os.getenv("SEND_INTERVAL", "500"))

VIDEOS_DIR = "videos"
STATE_FILE = "state.json"

# Optional: Bot2 can forward channel posts to a chat (for easy consumption)
# Put your own chat/group id here in env if you want forwarding:
# BOT2_FORWARD_CHAT_ID=123456789
BOT2_FORWARD_CHAT_ID = os.getenv("BOT2_FORWARD_CHAT_ID", "7970489926")
BOT2_FORWARD_CHAT_ID_INT = None
if BOT2_FORWARD_CHAT_ID:
    try:
        BOT2_FORWARD_CHAT_ID_INT = int(BOT2_FORWARD_CHAT_ID)
    except ValueError:
        logger.error(f"❌ BOT2_FORWARD_CHAT_ID غير صالح: {BOT2_FORWARD_CHAT_ID}")
        BOT2_FORWARD_CHAT_ID_INT = None

if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        print(f"❌ CHAT_ID غير صالح: {CHAT_ID}")
        raise SystemExit(1)
else:
    print("❌ CHAT_ID غير موجود")
    raise SystemExit(1)

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير محدد (حطه بالـ Environment Variables)")
if not BOT2_TOKEN:
    logger.warning("⚠️ BOT2_TOKEN غير محدد. Bot2 listener راح يكون متوقف.")

# ================== STATE ==================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_sent_index": -1, "videos_list": [], "last_sent_time": None}

def save_state(state):
    try:
        state["updated_at"] = datetime.now().isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ state.json: {e}")

# ================== VIDEOS ==================
def scan_videos():
    try:
        os.makedirs(VIDEOS_DIR, exist_ok=True)

        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"]
        videos = []

        for filename in os.listdir(VIDEOS_DIR):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                filepath = os.path.join(VIDEOS_DIR, filename)
                if os.path.exists(filepath):
                    caption_without_ext = os.path.splitext(filename)[0]
                    final_caption = caption_without_ext  # فقط اسم الفيديو بدون أي إضافة

                    videos.append({
                        "path": filepath,
                        "filename": filename,
                        "caption": final_caption[:1000],
                        "size": os.path.getsize(filepath)
                    })

        videos.sort(key=lambda x: x["filename"])

        if videos:
            total_size = sum(v["size"] for v in videos)
            logger.info(f"📊 تم العثور على {len(videos)} فيديو ({total_size/1024/1024:.1f} MB)")

        return videos
    except Exception as e:
        logger.error(f"خطأ في فحص الفيديوهات: {e}")
        return []

# ================== BOT1 (SENDER) ==================
async def init_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN غير محدد")

    bot = Bot(token=BOT_TOKEN)
    bot_info = await bot.get_me()
    logger.info(f"✅ Bot1 متصل: @{bot_info.username}")
    return bot

async def send_video(bot, video):
    try:
        # إرسال إلى الخاص
        logger.info(f"📤 إرسال إلى الخاص: {video['filename']}")
        with open(video["path"], "rb") as f:
            await bot.send_video(
                chat_id=CHAT_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )

        await asyncio.sleep(2)

        # إرسال إلى القناة
        logger.info(f"📤 إرسال إلى القناة: {video['filename']}")
        with open(video["path"], "rb") as f:
            message = await bot.send_video(
                chat_id=CHANNEL_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )

        file_id = message.video.file_id if message and message.video else None
        if file_id:
            logger.info(f"🆔 FILE_ID (channel post): {file_id}")

        return True

    except telegram_error.RetryAfter as e:
        logger.warning(f"⏳ RetryAfter: انتظر {e.retry_after} ثانية")
        await asyncio.sleep(e.retry_after)
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

# ================== BOT2 (LISTENER) ==================
async def bot2_on_channel_post(update, context):
    """
    Bot2 listens to channel posts. Make Bot2 ADMIN in the channel.
    This is what you want for n8n: bot2 receives the update with file_id.
    """
    msg = update.effective_message
    chat = update.effective_chat

    if not chat or chat.id != CHANNEL_ID:
        return

    if not msg:
        return

    # Video posted in channel
    if msg.video:
        file_id = msg.video.file_id
        logger.info(f"[BOT2] ✅ Received channel video. file_id={file_id}")

        # OPTIONAL: forward by file_id to a chat (if you set BOT2_FORWARD_CHAT_ID)
        if BOT2_FORWARD_CHAT_ID_INT:
            try:
                await context.bot.send_video(
                    chat_id=BOT2_FORWARD_CHAT_ID_INT,
                    video=file_id,
                    caption=msg.caption or ""
                )
                logger.info(f"[BOT2] ↪️ Forwarded to BOT2_FORWARD_CHAT_ID={BOT2_FORWARD_CHAT_ID_INT}")
            except Exception as e:
                logger.error(f"[BOT2] ❌ Forward failed: {e}")

def run_bot2_listener():
    if not BOT2_TOKEN:
        return

    try:
        application = Application.builder().token(BOT2_TOKEN).build()
        application.add_handler(MessageHandler(filters.ChatType.CHANNEL, bot2_on_channel_post))

        logger.info("👂 Bot2 listener started (polling). Add Bot2 as ADMIN in the channel.")
        # stop_signals=None to avoid signal issues in threads
        application.run_polling(stop_signals=None)
    except Exception as e:
        logger.error(f"❌ Bot2 listener crashed: {e}")

# ================== KEEP ALIVE FUNCTION ==================
def keep_alive():
    """Function to ping the Render app to keep it awake"""
    while True:
        try:
            response = requests.get(f"http://localhost:{PORT}/health", timeout=10)
            logger.info(f"Keep-alive ping response: {response.status_code}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(250)

# ================== MAIN LOOP ==================
async def main_loop():
    logger.info("🚀 بدء تشغيل البوت...")

    try:
        bot = await init_bot()
    except Exception as e:
        logger.error(f"❌ init_bot failed: {e}")
        return

    while True:
        try:
            state = load_state()
            videos = scan_videos()

            if not videos:
                logger.info("📭 لا توجد فيديوهات في المجلد")
                logger.info(f"📂 ضع الفيديوهات في: {os.path.abspath(VIDEOS_DIR)}")
                await asyncio.sleep(60)
                continue

            # تحديث القائمة إذا تغيرت
            current_list = [v["filename"] for v in videos]
            if state.get("videos_list") != current_list:
                logger.info(f"🔄 تم تحديث القائمة: {len(videos)} فيديو")
                state["videos_list"] = current_list
                state["last_sent_index"] = -1
                save_state(state)

            # الفيديو التالي
            next_index = (state.get("last_sent_index", -1) + 1) % len(videos)
            video_to_send = videos[next_index]

            logger.info(f"🎬 إرسال الفيديو ({next_index+1}/{len(videos)}): {video_to_send['filename']}")

            # الإرسال
            success = await send_video(bot, video_to_send)

            if success:
                logger.info(f"✅ تم إرسال '{video_to_send['filename']}' بنجاح.")
                state["last_sent_index"] = next_index
                state["last_sent_time"] = datetime.now().isoformat()
                save_state(state)

                logger.info(f"⏳ الانتظار {SEND_INTERVAL} ثانية للفيديو التالي...")
                logger.info(f"🔧 [DEBUG] SEND_INTERVAL = {SEND_INTERVAL}")
                await asyncio.sleep(SEND_INTERVAL)
            else:
                logger.warning(f"⚠️ فشل إرسال '{video_to_send['filename']}'. الانتظار 30 ثانية قبل إعادة المحاولة.")
                await asyncio.sleep(30)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"❌ خطأ في الحلقة الرئيسية: {e}")
            await asyncio.sleep(30)

# ================== RUN BOTH FLASK AND BOT ==================
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def run_keep_alive():
    keep_alive()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))

    print("=" * 50)
    print("🤖 Telegram Video Bot - Fixed Version")
    print(f"👤 Chat ID: {CHAT_ID}")
    print(f"📣 Channel ID: {CHANNEL_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"⏰ Interval: {SEND_INTERVAL} seconds")
    print(f"🌐 Port: {PORT}")
    print("=" * 50)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    bot2_thread = threading.Thread(target=run_bot2_listener, daemon=True)

    flask_thread.start()
    keep_alive_thread.start()
    bot2_thread.start()

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
