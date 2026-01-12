import os
import asyncio
import json
import logging
import threading
import sys
from datetime import datetime
from telegram import Bot, error as telegram_error
from pathlib import Path

# ================== CONFIG ==================
try:
    from flask import Flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("⚠️  Flask غير مثبت. سيتم تعطيل خادم الويب.")
    print("📦 قم بتثبيت Flask بإضافة 'Flask==3.0.0' إلى requirements.txt")

BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ")
CHAT_ID = os.getenv("CHAT_ID", "6968612778")

if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        print(f"❌ CHAT_ID غير صالح: {CHAT_ID}")
        sys.exit(1)
else:
    print("❌ CHAT_ID غير موجود")
    sys.exit(1)

VIDEOS_DIR = "videos"
SEND_INTERVAL = 300  # 5 دقائق
STATE_FILE = "state.json"
LOG_FILE = "video_bot.log"
MAX_RETRIES = 5
PORT = int(os.getenv("PORT", "10000"))

# الحدود القصوى لـ Telegram Bot API
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 جيجابايت
MAX_CAPTION_LENGTH = 1024  # حروف
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

# ================== WEB SERVER ==================
def run_web():
    if not FLASK_AVAILABLE:
        logger.warning("Flask غير متاح - خادم الويب معطل")
        return
    
    app = Flask(__name__)
    
    @app.route("/")
    def home():
        return """
        <html>
        <head><title>Telegram Video Bot</title></head>
        <body>
            <h1>✅ Telegram Video Bot is running</h1>
            <p>📁 Videos Directory: {}</p>
            <p>⏰ Interval: {} seconds</p>
            <p>📊 <a href="/status">View Status</a></p>
            <p>❤️ <a href="/health">Health Check</a></p>
        </body>
        </html>
        """.format(os.path.abspath(VIDEOS_DIR), SEND_INTERVAL), 200
    
    @app.route("/health")
    def health():
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200
    
    @app.route("/status")
    def status():
        state = load_state()
        videos = scan_videos()
        
        info = {
            "status": "running",
            "total_videos": len(videos),
            "last_sent_index": state.get("last_sent_index", -1),
            "last_sent_time": state.get("last_sent_time"),
            "next_video": None,
            "storage_info": {}
        }
        
        if videos:
            next_idx = (state.get("last_sent_index", -1) + 1) % len(videos)
            info["next_video"] = {
                "filename": videos[next_idx]["filename"],
                "size_mb": videos[next_idx]["size"] / (1024*1024)
            }
        
        # حساب مساحة التخزين
        total_size = 0
        for video in videos:
            total_size += video["size"]
        
        info["storage_info"] = {
            "total_size_gb": total_size / (1024*1024*1024),
            "total_size_mb": total_size / (1024*1024),
            "videos_count": len(videos)
        }
        
        return info, 200
    
    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"فشل تشغيل خادم الويب: {e}")

# ================== STATE ==================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة state.json: {e}")
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
        
        # جميع صيغ الفيديو المدعومة
        video_extensions = {
            '.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv',
            '.m4v', '.mpg', '.mpeg', '.3gp', '.ogg', '.ts', '.mts', '.m2ts'
        }
        
        videos = []
        for file in Path(VIDEOS_DIR).iterdir():
            if file.is_file() and file.suffix.lower() in video_extensions:
                size = file.stat().st_size
                
                if size > MAX_FILE_SIZE:
                    logger.warning(f"⚠️ الملف كبير جداً ({size/(1024*1024*1024):.2f}GB): {file.name}")
                    continue
                
                videos.append({
                    "path": str(file.absolute()),
                    "filename": file.name,
                    "caption": file.stem[:MAX_CAPTION_LENGTH],  # تقليل النص إذا كان طويلاً
                    "size": size,
                    "size_mb": size / (1024*1024),
                    "size_gb": size / (1024*1024*1024),
                    "modified": file.stat().st_mtime
                })
        
        # ترتيب حسب تاريخ التعديل (الأقدم أولاً)
        videos.sort(key=lambda x: x["modified"])
        
        logger.info(f"📊 تم العثور على {len(videos)} فيديو")
        if videos:
            total_size_gb = sum(v["size_gb"] for v in videos)
            logger.info(f"💾 الحجم الإجمالي: {total_size_gb:.2f} GB")
        
        return videos
    except Exception as e:
        logger.error(f"خطأ في فحص الفيديوهات: {e}")
        return []

# ================== BOT ==================
async def init_bot():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN غير محدد")
        raise ValueError("BOT_TOKEN غير محدد")
    
    for i in range(MAX_RETRIES):
        try:
            bot = Bot(token=BOT_TOKEN)
            bot_info = await bot.get_me()
            logger.info(f"✅ Bot متصل: @{bot_info.username} ({bot_info.first_name})")
            return bot
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بالبوت ({i+1}/{MAX_RETRIES}): {e}")
            if i < MAX_RETRIES - 1:
                wait_time = 5 * (i + 1)
                logger.info(f"⏳ الانتظار {wait_time} ثانية قبل إعادة المحاولة...")
                await asyncio.sleep(wait_time)
    
    raise RuntimeError(f"❌ فشل الاتصال بالبوت بعد {MAX_RETRIES} محاولات")

async def send_large_video(bot, video):
    """إرسال الفيديوهات الكبيرة (حتى 2GB)"""
    try:
        logger.info(f"📤 إرسال فيديو كبير: {video['filename']} ({video['size_mb']:.1f} MB)")
        
        # التحقق من حجم الملف
        if video['size'] > MAX_FILE_SIZE:
            logger.error(f"❌ الملف كبير جداً ({video['size_gb']:.2f}GB) الحد الأقصى 2GB")
            return False
        
        # زيادة مهلات الاتصال للفيديوهات الكبيرة
        timeout = max(120, video['size'] / (1024 * 1024) * 2)  # 2 ثانية لكل ميجابايت
        
        with open(video["path"], "rb") as f:
            await bot.send_video(
                chat_id=CHAT_ID,
                video=f,
                caption=video["caption"],
                supports_streaming=True,
                read_timeout=timeout,
                write_timeout=timeout,
                connect_timeout=60,
                pool_timeout=60,
                api_kwargs={
                    'timeout': timeout,
                    'connect_timeout': 60,
                    'read_timeout': timeout,
                    'write_timeout': timeout
                }
            )
        
        logger.info(f"✅ تم إرسال الفيديو بنجاح: {video['filename']}")
        return True
        
    except telegram_error.RetryAfter as e:
        wait_time = e.retry_after
        logger.warning(f"⏳ تم طلب الانتظار من تلغرام: {wait_time} ثانية")
        await asyncio.sleep(wait_time)
        return False
        
    except (telegram_error.TimedOut, telegram_error.NetworkError) as e:
        logger.warning(f"🌐 مشكلة شبكة: {e}")
        return False
        
    except telegram_error.TelegramError as e:
        error_msg = str(e).lower()
        if "file is too big" in error_msg:
            logger.error("📦 الملف أكبر من 2GB الحد الأقصى للتلغرام")
        elif "wrong file identifier" in error_msg:
            logger.error("🆔 خطأ في معرّف الملف")
        else:
            logger.error(f"❌ خطأ في تلغرام: {e}")
        return False
        
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        return False

async def send_video_with_retry(bot, video, max_attempts=5):
    """إرسال الفيديو مع إعادة المحاولة"""
    for attempt in range(max_attempts):
        logger.info(f"🔄 محاولة {attempt+1}/{max_attempts}: {video['filename']}")
        
        success = await send_large_video(bot, video)
        if success:
            return True
        
        if attempt < max_attempts - 1:
            wait_time = 30 * (attempt + 1)
            logger.info(f"⏳ إعادة المحاولة بعد {wait_time} ثانية...")
            await asyncio.sleep(wait_time)
    
    logger.error(f"❌ فشل إرسال الفيديو بعد {max_attempts} محاولات: {video['filename']}")
    return False

# ================== MAIN LOOP ==================
async def forever():
    logger.info("🚀 بدء تشغيل البوت...")
    logger.info(f"💾 الحد الأقصى لحجم الفيديو: {MAX_FILE_SIZE/(1024*1024*1024):.1f} GB")
    
    try:
        bot = await init_bot()
    except Exception as e:
        logger.error(f"❌ فشل تهيئة البوت: {e}")
        return
    
    logger.info(f"📁 مجلد الفيديوهات: {os.path.abspath(VIDEOS_DIR)}")
    logger.info(f"⏰ فترة الإرسال: {SEND_INTERVAL} ثانية ({SEND_INTERVAL/60:.1f} دقيقة)")
    
    while True:
        try:
            state = load_state()
            videos = scan_videos()
            
            if not videos:
                logger.info("📭 لا توجد فيديوهات في المجلد")
                logger.info(f"📂 ضع الفيديوهات في: {os.path.abspath(VIDEOS_DIR)}")
                await asyncio.sleep(60)
                continue
            
            # التحقق من تغيير قائمة الفيديوهات
            current_video_list = [v["filename"] for v in videos]
            if state["videos_list"] != current_video_list:
                logger.info(f"🔄 تم اكتشاف {len(videos)} فيديوهات جديدة/محدثة")
                state["videos_list"] = current_video_list
                state["last_sent_index"] = -1
                save_state(state)
            
            # تحديد الفيديو التالي
            idx = (state.get("last_sent_index", -1) + 1) % len(videos)
            next_video = videos[idx]
            
            logger.info(f"🎬 الفيديو الحالي ({idx+1}/{len(videos)}):")
            logger.info(f"   📝 الاسم: {next_video['filename']}")
            logger.info(f"   📊 الحجم: {next_video['size_mb']:.1f} MB ({next_video['size_gb']:.2f} GB)")
            logger.info(f"   ⏱️  المدة: {SEND_INTERVAL} ثانية بين الفيديوهات")
            
            # إرسال الفيديو
            start_time = datetime.now()
            if await send_video_with_retry(bot, next_video):
                state["last_sent_index"] = idx
                state["last_sent_time"] = datetime.now().isoformat()
                save_state(state)
                
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ تم الإرسال بنجاح في {elapsed:.1f} ثانية")
                
                next_idx = (idx + 1) % len(videos)
                logger.info(f"⏭️  الفيديو التالي: {videos[next_idx]['filename']}")
                
                wait_time = max(SEND_INTERVAL - elapsed, 60)
                logger.info(f"⏰ الانتظار {wait_time:.1f} ثانية حتى الفيديو التالي")
                await asyncio.sleep(wait_time)
            else:
                logger.warning("⚠️ تخطي الفيديو والمحاولة للفيديو التالي")
                state["last_sent_index"] = idx  # تحديث الفهرس حتى لو فشل
                save_state(state)
                await asyncio.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("⏹️ إيقاف البوت بواسطة المستخدم")
            break
        except Exception as e:
            logger.error(f"❌ خطأ في الحلقة الرئيسية: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info("⏳ إعادة المحاولة بعد 30 ثانية...")
            await asyncio.sleep(30)

# ================== START ==================
if __name__ == "__main__":
    # طباعة معلومات النظام
    logger.info("=" * 50)
    logger.info("🤖 Telegram Video Bot - الإصدار مع دعم 2GB")
    logger.info("=" * 50)
    
    # بدء خادم الويب في thread منفصل
    if FLASK_AVAILABLE:
        web_thread = threading.Thread(target=run_web, daemon=True)
        web_thread.start()
        logger.info(f"🌐 خادم الويب يعمل على: http://0.0.0.0:{PORT}")
    else:
        logger.warning("⚠️ خادم الويب معطل - قم بتثبيت Flask")
    
    # بدء البوت
    try:
        asyncio.run(forever())
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        import traceback
        logger.error(traceback.format_exc())
