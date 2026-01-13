import subprocess
import sys

# تثبيت المكتبات تلقائيًا
def install_packages():
    packages = ['flask', 'python-telegram-bot', 'requests']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

install_packages()

# ثم استمر في باقي imports
from flask import Flask, jsonify, request
import os
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot, error as telegram_error
import threading
import requests

PORT = int(os.environ.get('PORT', 10000))  # تعريف PORT هنا
# [باقي الكود كما هو...]
# ================== FLASK APP ==================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "message": "Telegram Video Bot is active",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ")
CHAT_ID = os.getenv("CHAT_ID", "6968612778")

if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        print(f"❌ CHAT_ID غير صالح: {CHAT_ID}")
        exit(1)
else:
    print("❌ CHAT_ID غير موجود")
    exit(1)

VIDEOS_DIR = "videos"
SEND_INTERVAL = int(os.getenv("SEND_INTERVAL", "300"))
STATE_FILE = "state.json"
LOG_FILE = "bot.log"

logger.info(f"⏳ الانتظار {SEND_INTERVAL} ثانية للفيديو التالي...")
logger.info(f"🔧 [DEBUG] SEND_INTERVAL = {SEND_INTERVAL}")
await asyncio.sleep(SEND_INTERVAL)
# ============================================

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== STATE ==================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
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
# ================== VIDEOS ==================
# ================== VIDEOS ==================
def scan_videos():
    try:
        os.makedirs(VIDEOS_DIR, exist_ok=True)
        
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']
        videos = []
        
        for filename in os.listdir(VIDEOS_DIR):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                filepath = os.path.join(VIDEOS_DIR, filename)
                if os.path.exists(filepath):
                    # Remove extension from caption
                    caption_without_ext = os.path.splitext(filename)[0]
                    # Add custom text
                    final_caption = caption_without_ext  # فقط اسم الفيديو بدون أي إضافة
                    
                    videos.append({
                        "path": filepath,
                        "filename": filename,
                        "caption": final_caption[:1000],  # Limit to 1000 chars
                        "size": os.path.getsize(filepath)
                    })
        
        # ترتيب أبجدي
        videos.sort(key=lambda x: x["filename"])
        
        if videos:
            total_size = sum(v["size"] for v in videos)
            logger.info(f"📊 تم العثور على {len(videos)} فيديو ({total_size/1024/1024:.1f} MB)")
        
        return videos
    except Exception as e:
        logger.error(f"خطأ في فحص الفيديوهات: {e}")
        return []

# ================== BOT ==================
async def init_bot():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN غير محدد")
        raise ValueError("BOT_TOKEN غير محدد")
    
    try:
        bot = Bot(token=BOT_TOKEN)
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot متصل: @{bot_info.username}")
        return bot
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بالبوت: {e}")
        raise

async def send_video(bot, video):
    try:
        # =========================
        # إرسال إلى الخاص
        # =========================
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

        # تأخير صغير لتجنب flood control
        await asyncio.sleep(2)

        # =========================
        # إرسال إلى القناة
        # =========================
        CHANNEL_ID = -1003218943676
        logger.info(f"📤 إرسال إلى القناة: {video['filename']}")
        with open(video["path"], "rb") as f:
            message = await bot.send_video(
                chat_id=CHANNEL_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True
            )

        file_id = message.video.file_id
        logger.info(f"🆔 FILE_ID: {file_id}")

        # =========================
        # 🔥 هذا السطر المهم لـ n8n
        # إرسال نفس الفيديو للبوت نفسه
        # =========================
        await bot.send_video(
            chat_id=bot.id,
            video=file_id,
            caption=video["caption"]
        )

        # كل شيء تم بنجاح
        return True

    except telegram_error.RetryAfter as e:
        logger.warning(f"⏳ انتظر {e.retry_after} ثانية")
        await asyncio.sleep(e.retry_after)
        return False

    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

# ================== KEEP ALIVE FUNCTION ==================
def keep_alive():
    """Function to ping the Render app to keep it awake"""
    while True:
        try:
            response = requests.get(f"http://localhost:{PORT}/health")
            logger.info(f"Keep-alive ping response: {response.status_code}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(250)  # Ping every ~4 minutes

# ================== MAIN LOOP ==================
# ================== MAIN LOOP ==================
async def main_loop():
    logger.info("🚀 بدء تشغيل البوت...")
    
    try:
        bot = await init_bot()
    except:
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
            if state["videos_list"] != current_list:
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
                await asyncio.sleep(SEND_INTERVAL) # انتظار طويل عند النجاح
            else:
                logger.warning(f"⚠️ فشل إرسال '{video_to_send['filename']}'. الانتظار 30 ثانية قبل إعادة المحاولة.")
                await asyncio.sleep(30) # انتظار قصير عند الفشل لتجنب المشاكل
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"❌ خطأ في الحلقة الرئيسية: {e}")
            await asyncio.sleep(30) # انتظار عند حدوث خطأ غير متوقع

# ================== RUN BOTH FLASK AND BOT ==================
def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_keep_alive():
    keep_alive()

if __name__ == "__main__":
    # Get port from environment variable or default to 10000
    PORT = int(os.environ.get('PORT', 10000))
    
    # طباعة معلومات البدء
    print("=" * 50)
    print("🤖 Telegram Video Bot - Advanced Version")
    print(f"👤 Chat ID: {CHAT_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"⏰ Interval: {SEND_INTERVAL} seconds")
    print(f"🌐 Port: {PORT}")
    print("=" * 50)
    
    # Create threads
    flask_thread = threading.Thread(target=run_flask)
    keep_alive_thread = threading.Thread(target=run_keep_alive)
    
    # Start threads
    flask_thread.daemon = True
    keep_alive_thread.daemon = True
    
    flask_thread.start()
    keep_alive_thread.start()
    
    # Run the main loop
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
