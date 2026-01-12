import os
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot, error as telegram_error

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
SEND_INTERVAL = 300  # 5 دقائق
STATE_FILE = "state.json"
LOG_FILE = "bot.log"
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
def scan_videos():
    try:
        os.makedirs(VIDEOS_DIR, exist_ok=True)
        
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']
        videos = []
        
        for filename in os.listdir(VIDEOS_DIR):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                filepath = os.path.join(VIDEOS_DIR, filename)
                if os.path.exists(filepath):
                    videos.append({
                        "path": filepath,
                        "filename": filename,
                        "caption": filename[:1000],
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
        logger.info(f"📤 جاري إرسال: {video['filename']}")
        
        with open(video["path"], "rb") as f:
            await bot.send_video(
                chat_id=CHAT_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )
        
        logger.info(f"✅ تم الإرسال: {video['filename']}")
        return True
        
    except telegram_error.RetryAfter as e:
        logger.warning(f"⏳ انتظر {e.retry_after} ثانية")
        await asyncio.sleep(e.retry_after)
        return False
        
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

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
            if await send_video(bot, video_to_send):
                state["last_sent_index"] = next_index
                state["last_sent_time"] = datetime.now().isoformat()
                save_state(state)
            
            logger.info(f"⏳ الانتظار {SEND_INTERVAL} ثانية للفيديو التالي...")
            await asyncio.sleep(SEND_INTERVAL)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"❌ خطأ في الحلقة الرئيسية: {e}")
            await asyncio.sleep(30)

# ================== START ==================
if __name__ == "__main__":
    # طباعة معلومات البدء
    print("=" * 50)
    print("🤖 Telegram Video Bot")
    print(f"👤 Chat ID: {CHAT_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"⏰ Interval: {SEND_INTERVAL} seconds")
    print("=" * 50)
    
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
