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
from telegram import Bot, Update, error as telegram_error
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading
import requests

PORT = int(os.environ.get('PORT', 10000))  # تعريف PORT هنا

# ================== FLASK APP ==================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "message": "Telegram Listener Bot is active",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "7970489926:AAGnzN-CGai1kpFs1gGOmykqPE4y7Rv0Bvk")
CHAT_ID = os.getenv("CHAT_ID", "-1003218943676")  # تأكد من تعيينه إلى معرف القناة

if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        print(f"❌ CHAT_ID غير صالح: {CHAT_ID}")
        exit(1)
else:
    print("❌ CHAT_ID غير موجود")
    exit(1)

LOG_FILE = "listener_bot.log"

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

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلا بك! أنا مستعد لأستقبال الفيديوهات والكابشنة من القناة.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        video = update.message.video
        caption = update.message.caption if update.message.caption else "بدون كابشن"
        file_id = video.file_id
        
        logger.info(f"📥 استلمت فيديو: {video.file_name} مع كابشن: {caption}")
        logger.info(f"🆔 FILE_ID: {file_id}")

        # إرسال رسالة تأكيد إلى حسابك الخاص (اختياري)
        OWNER_CHAT_ID = 6968612778  # معرف حسابك الخاص
        confirmation_message = f"📥 استلمت فيديو:\n{caption}\nFILE_ID: {file_id}"
        await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=confirmation_message)

    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الفيديو: {e}")

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

# ================== MAIN ==================
def main():
    logger.info("🚀 بدء تشغيل البوت الاستماعي...")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    video_handler = MessageHandler(filters.VIDEO, handle_video)
    
    application.add_handler(start_handler)
    application.add_handler(video_handler)
    
    # Run the bot
    application.run_polling()

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
    print("🤖 Telegram Listener Bot - Advanced Version")
    print(f"👤 Chat ID: {CHAT_ID}")
    print(f"🌐 Port: {PORT}")
    print("=" * 50)
    
    # Create threads
    flask_thread = threading.Thread(target=run_flask)
    keep_alive_thread = threading.Thread(target=run_keep_alive)
    bot_thread = threading.Thread(target=main)
    
    # Start threads
    flask_thread.daemon = True
    keep_alive_thread.daemon = True
    bot_thread.daemon = True
    
    flask_thread.start()
    keep_alive_thread.start()
    bot_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(3600)  # Sleep indefinitely
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
