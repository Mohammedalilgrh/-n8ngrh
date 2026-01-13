import subprocess
import sys
import os
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot, error as telegram_error
from flask import Flask, jsonify
import threading
import requests
import py7zr

# ================== AUTO INSTALL ==================
def install_packages():
    packages = ['flask', 'python-telegram-bot', 'requests', 'py7zr']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

install_packages()

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("8212401543:AAFZNuyv5Ua17hnJG4XHdB5JuRwZVCwJPCM")
CHAT_ID = int(os.getenv("CHAT_ID", "6968612778"))
CHANNEL_ID = -1003218943676

VIDEOS_DIR = "videos"
ARCHIVE_PATH = os.path.join(VIDEOS_DIR, "videos.7z")
EXTRACT_DIR = os.path.join(VIDEOS_DIR, "extracted")

SEND_INTERVAL_MINUTES = 5
SEND_INTERVAL = SEND_INTERVAL_MINUTES * 60

STATE_FILE = "state.json"
LOG_FILE = "bot.log"
PORT = int(os.environ.get("PORT", 10000))

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

# ================== FLASK ==================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "running"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

# ================== STATE ==================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_sent_index": -1, "videos": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ================== EXTRACT 7Z ==================
def extract_7z():
    if not os.path.exists(ARCHIVE_PATH):
        logger.warning("📦 ملف videos.7z غير موجود")
        return

    os.makedirs(EXTRACT_DIR, exist_ok=True)

    if os.listdir(EXTRACT_DIR):
        return  # مستخرج سابقًا

    logger.info("📦 فك ضغط videos.7z ...")
    with py7zr.SevenZipFile(ARCHIVE_PATH, mode="r") as z:
        z.extractall(EXTRACT_DIR)

    logger.info("✅ تم فك الضغط")

# ================== SCAN VIDEOS ==================
def scan_videos():
    videos = []
    for root, _, files in os.walk(EXTRACT_DIR):
        for file in files:
            if file.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".webm")):
                path = os.path.join(root, file)
                videos.append({
                    "path": path,
                    "filename": file,
                    "caption": os.path.splitext(file)[0]
                })
    videos.sort(key=lambda x: x["filename"])
    return videos

# ================== BOT ==================
async def init_bot():
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"🤖 Bot @{me.username} متصل")
    return bot

async def send_video(bot, video):
    with open(video["path"], "rb") as f:
        msg = await bot.send_video(
            chat_id=CHANNEL_ID,
            video=f,
            caption=video["caption"],
            supports_streaming=True
        )

    logger.info(f"🆔 FILE_ID: {msg.video.file_id}")
    return True

# ================== MAIN LOOP ==================
async def main_loop():
    extract_7z()
    bot = await init_bot()

    while True:
        state = load_state()
        videos = scan_videos()

        if not videos:
            logger.info("📭 لا توجد فيديوهات")
            await asyncio.sleep(60)
            continue

        idx = (state["last_sent_index"] + 1) % len(videos)
        video = videos[idx]

        logger.info(f"🎬 إرسال: {video['filename']}")

        if await send_video(bot, video):
            state["last_sent_index"] = idx
            save_state(state)

        logger.info(f"⏳ انتظار {SEND_INTERVAL_MINUTES} دقائق")
        await asyncio.sleep(SEND_INTERVAL)

# ================== KEEP ALIVE ==================
def keep_alive():
    while True:
        try:
            requests.get(f"http://localhost:{PORT}/health")
        except:
            pass
        time.sleep(240)

# ================== RUN ==================
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    asyncio.run(main_loop())
