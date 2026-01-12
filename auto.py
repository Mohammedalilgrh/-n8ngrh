import os
import asyncio
import json
import logging
import threading
from datetime import datetime
from flask import Flask
from telegram import Bot, error as telegram_error

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ")
CHAT_ID = int(os.getenv("CHAT_ID", "6968612778"))

VIDEOS_DIR = "videos"
SEND_INTERVAL = 300
STATE_FILE = "state.json"
LOG_FILE = "bot.log"
PORT = int(os.getenv("PORT", 8080))  # ⚠️ غيرنا المنفذ إلى 8080
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

# ================== FLASK APP ==================
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
    <head><title>Telegram Video Bot</title></head>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🤖 Telegram Video Bot</h1>
        <p>✅ البوت يعمل بنجاح</p>
        <p>📁 مجلد الفيديوهات: {}</p>
        <p>⏰ الفاصل الزمني: {} ثانية</p>
        <p>🔄 <a href="/status">حالة البوت</a></p>
        <p>❤️ <a href="/health">فحص الصحة</a></p>
    </body>
    </html>
    """.format(VIDEOS_DIR, SEND_INTERVAL)

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200

@app.route('/status')
def status():
    state = load_state()
    videos = scan_videos()
    
    return {
        "status": "running",
        "total_videos": len(videos),
        "last_sent": state.get("last_sent_time"),
        "next_index": (state.get("last_sent_index", -1) + 1) % max(len(videos), 1)
    }, 200

def run_flask():
    """تشغيل Flask"""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ... باقي الدوال نفسها مثل load_state, save_state, scan_videos ...

async def bot_loop():
    """الحلقة الرئيسية للبوت"""
    logger.info("🤖 بدء تشغيل بوت التلغرام...")
    
    try:
        bot = Bot(token=BOT_TOKEN)
        bot_info = await bot.get_me()
        logger.info(f"✅ متصل كـ: @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ فشل الاتصال: {e}")
        return
    
    while True:
        try:
            state = load_state()
            videos = scan_videos()
            
            if not videos:
                logger.info("📭 لا توجد فيديوهات")
                await asyncio.sleep(60)
                continue
            
            next_idx = (state.get("last_sent_index", -1) + 1) % len(videos)
            video = videos[next_idx]
            
            logger.info(f"🎬 إرسال: {video['filename']}")
            
            try:
                with open(video["path"], "rb") as f:
                    await bot.send_video(
                        chat_id=CHAT_ID,
                        video=f,
                        caption=video["caption"],
                        supports_streaming=True
                    )
                
                state["last_sent_index"] = next_idx
                state["last_sent_time"] = datetime.now().isoformat()
                save_state(state)
                logger.info("✅ تم الإرسال")
                
            except Exception as e:
                logger.error(f"❌ خطأ في الإرسال: {e}")
            
            await asyncio.sleep(SEND_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحلقة: {e}")
            await asyncio.sleep(30)

async def main():
    """الدالة الرئيسية"""
    # بدء Flask في thread منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 خادم الويب يعمل على المنفذ {PORT}")
    
    # بدء بوت التلغرام
    await bot_loop()

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 بدء Telegram Video Bot")
    print(f"🌐 Port: {PORT}")
    print("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 إيقاف البوت")
