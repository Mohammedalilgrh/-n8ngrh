import os
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

# ================== CONFIG ==================
BOT_TOKEN = "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ"
CHAT_ID = 6968612778
VIDEOS_DIR = "videos"
SEND_INTERVAL = 300  # 5 دقائق بالثواني (300 ثانية)
STATE_FILE = "state.json"
LOG_FILE = "video_bot.log"
MAX_RETRIES = 5  # الحد الأقصى لمحاولات إعادة الاتصال
# ============================================

# إعداد التسجيل (Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ================== وظائف التخزين ==================
def load_state():
    """تحميل حالة آخر فيديو تم إرساله"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding='utf-8') as f:
                state = json.load(f)
                # التأكد من أن الحالة تحتوي على الهيكل الصحيح
                if "last_sent_index" not in state:
                    state["last_sent_index"] = -1
                if "videos_list" not in state:
                    state["videos_list"] = []
                if "last_successful_send" not in state:
                    state["last_successful_send"] = None
                return state
        return {"last_sent_index": -1, "videos_list": [], "last_successful_send": None}
    except Exception as e:
        logger.error(f"خطأ في تحميل الحالة: {e}")
        return {"last_sent_index": -1, "videos_list": [], "last_successful_send": None}

def save_state(state):
    """حفظ حالة آخر فيديو تم إرساله"""
    try:
        # إضافة وقت آخر حفظ للحالة
        state["last_state_save"] = datetime.now().isoformat()
        with open(STATE_FILE, "w", encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ الحالة: {e}")

# ================== وظائف الفيديوهات ==================
def scan_videos():
    """قراءة كل ملفات الفيديو في مجلد videos"""
    if not os.path.exists(VIDEOS_DIR):
        os.makedirs(VIDEOS_DIR)
        logger.info(f"تم إنشاء المجلد {VIDEOS_DIR}. ضع الفيديوهات داخله.")
        return []

    videos = []
    try:
        video_files = []
        for f in os.listdir(VIDEOS_DIR):
            if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")):
                video_files.append(f)
        
        # ترتيب أبجدي للتسلسل الثابت
        video_files.sort()
        
        for f in video_files:
            path = os.path.join(VIDEOS_DIR, f)
            caption = os.path.splitext(f)[0]  # اسم الملف بدون الامتداد ككابشن
            videos.append({
                "path": path, 
                "caption": caption, 
                "filename": f,
                "size": os.path.getsize(path) if os.path.exists(path) else 0,
                "modified_time": os.path.getmtime(path) if os.path.exists(path) else 0
            })
        
        logger.info(f"تم العثور على {len(videos)} فيديو")
        return videos
        
    except Exception as e:
        logger.error(f"خطأ في قراءة الفيديوهات: {e}")
        return []

def get_video_index_by_filename(videos, filename):
    """الحصول على индекс الفيديو بناءً على اسم الملف"""
    for i, video in enumerate(videos):
        if video["filename"] == filename:
            return i
    return -1

# ================== إرسال الفيديوهات ==================
async def initialize_bot():
    """تهيئة البوت مع إعادة المحاولة"""
    for attempt in range(MAX_RETRIES):
        try:
            bot = Bot(token=BOT_TOKEN)
            # اختبار اتصال البوت
            me = await bot.get_me()
            logger.info(f"تم تهيئة البوت بنجاح: @{me.username}")
            return bot
        except Exception as e:
            logger.error(f"محاولة {attempt + 1}/{MAX_RETRIES} فشلت في تهيئة البوت: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(10 * (attempt + 1))
            else:
                raise Exception(f"فشل تهيئة البوت بعد {MAX_RETRIES} محاولات")

async def send_video_safely(bot, video_info):
    """إرسال فيديو مع معالجة الأخطاء وإعادة المحاولة"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # التحقق من وجود الملف
            if not os.path.exists(video_info["path"]):
                logger.error(f"الملف غير موجود: {video_info['path']}")
                return False
            
            # التحقق من حجم الملف
            if video_info["size"] == 0:
                logger.error(f"حجم الملف صفر: {video_info['path']}")
                return False
            
            logger.info(f"محاولة إرسال الفيديو: {video_info['filename']} (المحاولة {attempt + 1})")
            
            with open(video_info["path"], "rb") as vfile:
                await bot.send_video(
                    chat_id=CHAT_ID,
                    video=vfile,
                    caption=video_info["caption"],
                    timeout=120,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=120
                )
            
            logger.info(f"تم إرسال الفيديو بنجاح: {video_info['filename']}")
            return True
            
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(f"تم طلب الانتظار {wait_time} ثانية. المحاولة {attempt + 1}")
            await asyncio.sleep(wait_time)
            
        except (TimedOut, NetworkError) as e:
            logger.warning(f"مشكلة في الشبكة/انتهت المهلة. المحاولة {attempt + 1}: {e}")
            await asyncio.sleep(10 * (attempt + 1))
            
        except TelegramError as e:
            logger.error(f"خطأ تيليجرام في المحاولة {attempt + 1}: {e}")
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"خطأ غير متوقع في المحاولة {attempt + 1}: {e}")
            await asyncio.sleep(10)
    
    return False

async def video_sending_cycle(bot):
    """دورة إرسال الفيديوهات الرئيسية"""
    state = load_state()
    videos = scan_videos()
    
    if not videos:
        logger.info("لا توجد فيديوهات في المجلد.")
        return state, False
    
    # تحديث قائمة الفيديوهات إذا تغيرت
    current_filenames = [v["filename"] for v in videos]
    if state["videos_list"] != current_filenames:
        logger.info("تم اكتشاف تغيير في قائمة الفيديوهات")
        
        # إذا كانت القائمة القديمة فارغة، نبدأ من الأول
        if not state["videos_list"]:
            next_index = 0
        else:
            # البحث عن آخر فيديو تم إرساله في القائمة الجديدة
            last_sent_filename = None
            if state["last_sent_index"] >= 0 and state["last_sent_index"] < len(state["videos_list"]):
                last_sent_filename = state["videos_list"][state["last_sent_index"]]
            
            if last_sent_filename and last_sent_filename in current_filenames:
                next_index = (current_filenames.index(last_sent_filename) + 1) % len(current_filenames)
            else:
                next_index = 0  # ابدأ من الأول إذا لم يتم العثور على الفيديو الأخير
        
        state["videos_list"] = current_filenames
        state["last_sent_index"] = next_index - 1  # سيتم زيادة +1 لاحقاً
        logger.info(f"تم تحديث الفهرس إلى: {state['last_sent_index']}")
    
    # تحديد الفيديو التالي للإرسال
    next_index = (state["last_sent_index"] + 1) % len(videos)
    next_video = videos[next_index]
    
    # محاولة الإرسال
    success = await send_video_safely(bot, next_video)
    
    if success:
        # تحديث الحالة بعد الإرسال الناجح
        state["last_sent_index"] = next_index
        state["last_successful_send"] = datetime.now().isoformat()
        save_state(state)
        logger.info(f"تم تحديث الفهرس إلى: {next_index}")
        return state, True
    else:
        logger.error(f"فشل إرسال الفيديو: {next_video['filename']}")
        return state, False

async def main_forever():
    """الدالة الرئيسية التي تعمل للأبد"""
    logger.info("=== بدء تشغيل بوت إرسال الفيديوهات (وضع Forever) ===")
    
    bot = None
    consecutive_failures = 0
    
    while True:
        try:
            # إعادة تهيئة البوت إذا لزم الأمر
            if bot is None:
                bot = await initialize_bot()
                consecutive_failures = 0
            
            # تنفيذ دورة الإرسال
            state, success = await video_sending_cycle(bot)
            
            if success:
                consecutive_failures = 0
                logger.info(f"الانتظار {SEND_INTERVAL} ثانية قبل الفيديو التالي...")
                await asyncio.sleep(SEND_INTERVAL)
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.warning("3 محاولات فاشلة متتالية، إعادة تهيئة البوت...")
                    bot = None
                    await asyncio.sleep(30)
                else:
                    logger.info("انتظار 60 ثانية قبل المحاولة مرة أخرى...")
                    await asyncio.sleep(60)
                    
        except KeyboardInterrupt:
            logger.info("تم إيقاف البوت بواسطة المستخدم")
            break
            
        except Exception as e:
            logger.error(f"خطأ غير متوقع في الدورة الرئيسية: {e}")
            bot = None  # إعادة تهيئة البوت في المرة القادمة
            consecutive_failures += 1
            wait_time = min(60 * consecutive_failures, 300)  # زيادة وقت الانتظار تدريجياً
            logger.info(f"انتظار {wait_time} ثانية قبل إعادة المحاولة...")
            await asyncio.sleep(wait_time)

# ================== تشغيل البرنامج ==================
if __name__ == "__main__":
    try:
        # تشغيل الدالة الرئيسية للأبد
        asyncio.run(main_forever())
    except KeyboardInterrupt:
        logger.info("تم إيقاف البوت بشكل نظيف")
    except Exception as e:
        logger.error(f"خطأ قاتل: {e}")
    finally:
        logger.info("=== نهاية تشغيل البوت ===")
