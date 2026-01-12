import os
import asyncio
import json
import logging
import threading
from datetime import datetime
from flask import Flask
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ")  # القيمة الافتراضية للتنمية
CHAT_ID = int(os.getenv("CHAT_ID", "6968612778"))  # تحويل إلى int
VIDEOS_DIR = "videos"
SEND_INTERVAL = 300
STATE_FILE = "state.json"
LOG_FILE = "video_bot.log"
MAX_RETRIES = 5
PORT = int(os.getenv("PORT", "10000"))
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
app = Flask(__name__)

@app.route("/")
def home():
    return "Telegram Video Bot is running ✅", 200

def run_web():
    app.run(host="0.0.0.0", port=PORT)

# ================== STATE ==================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"last_sent_index": -1, "videos_list": []}

def save_state(state):
    state["updated_at"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ================== VIDEOS ==================
def scan_videos():
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    files = sorted([
        f for f in os.listdir(VIDEOS_DIR)
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm"))
    ])
    return [{
        "path": os.path.join(VIDEOS_DIR, f),
        "caption": os.path.splitext(f)[0],
        "filename": f
    } for f in files]

# ================== BOT ==================
async def init_bot():
    for i in range(MAX_RETRIES):
        try:
            bot = Bot(BOT_TOKEN)
            await bot.get_me()
            logger.info("Bot connected successfully")
            return bot
        except Exception as e:
            logger.error(f"Bot init failed ({i+1}): {e}")
            await asyncio.sleep(5 * (i + 1))
    raise RuntimeError("Bot failed permanently")

async def send_video(bot, video):
    for _ in range(3):
        try:
            with open(video["path"], "rb") as f:
                await bot.send_video(
                    chat_id=CHAT_ID,
                    video=f,
                    caption=video["caption"]
                )
            return True
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except (TimedOut, NetworkError):
            await asyncio.sleep(10)
        except TelegramError as e:
            logger.error(e)
            await asyncio.sleep(10)
    return False

# ================== MAIN LOOP ==================
async def forever():
    bot = await init_bot()

    while True:
        try:
            state = load_state()
            videos = scan_videos()

            if not videos:
                logger.info("No videos found")
                await asyncio.sleep(60)
                continue

            if state["videos_list"] != [v["filename"] for v in videos]:
                state["videos_list"] = [v["filename"] for v in videos]
                state["last_sent_index"] = -1

            idx = (state["last_sent_index"] + 1) % len(videos)

            if await send_video(bot, videos[idx]):
                state["last_sent_index"] = idx
                save_state(state)
                logger.info("Video sent successfully")

            await asyncio.sleep(SEND_INTERVAL)

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(30)

# ================== START ==================
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(forever())
