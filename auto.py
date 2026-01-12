import os
import asyncio
import json
import random
from telegram import Bot
from telegram.error import TelegramError

# ================== CONFIG ==================
BOT_TOKEN = "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ"  # ضع توكن البوت الحقيقي هنا
CHAT_ID = 6968612778  # chat id الخاص بك
VIDEOS_DIR = "videos"
DEFAULT_SEND_INTERVAL = 50  # ثواني بين كل فيديو بشكل افتراضي
STATE_FILE = "state.json"  # لحفظ حالة آخر فيديو تم إرساله
# ============================================

bot = Bot(token=BOT_TOKEN)

# ================== وظائف التخزين ==================
def load_state():
    """ تحميل حالة آخر فيديو تم إرساله """
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_sent": None}

def save_state(state):
    """ حفظ حالة آخر فيديو تم إرساله """
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ================== وظائف الفيديوهات ==================
def scan_videos():
    """
    قراءة كل ملفات الفيديو في مجلد videos
    """
    if not os.path.exists(VIDEOS_DIR):
        os.makedirs(VIDEOS_DIR)
        print(f"تم إنشاء المجلد {VIDEOS_DIR}. ضع الفيديوهات داخله.")
        return []

    videos = []
    for f in os.listdir(VIDEOS_DIR):
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
            path = os.path.join(VIDEOS_DIR, f)
            caption = os.path.splitext(f)[0]  # اسم الملف بدون الامتداد ككابشن
            videos.append({"path": path, "caption": caption, "interval": DEFAULT_SEND_INTERVAL})
    return videos

# ================== إرسال الفيديوهات ==================
async def send_videos_forever():
    state = load_state()

    while True:
        videos = scan_videos()
        if not videos:
            print("لا توجد فيديوهات في المجلد.")
            await asyncio.sleep(5)
            continue

        # ترتيب عشوائي لكل دورة
        random.shuffle(videos)

        # إذا كان هناك فيديو تم إرساله سابقًا، نبدأ بعده
        start_index = 0
        if state.get("last_sent"):
            for i, v in enumerate(videos):
                if v["path"] == state["last_sent"]:
                    start_index = (i + 1) % len(videos)
                    break

        # إرسال الفيديوهات
        for i in range(len(videos)):
            video = videos[(start_index + i) % len(videos)]
            try:
                with open(video["path"], "rb") as vfile:
                    await bot.send_video(
                        chat_id=CHAT_ID,
                        video=vfile,
                        caption=video["caption"]
                    )
                print(f"تم إرسال الفيديو: {video['path']} مع الكابشن: {video['caption']}")
                # تحديث الحالة بعد كل فيديو
                state["last_sent"] = video["path"]
                save_state(state)
            except TelegramError as e:
                print(f"خطأ أثناء إرسال الفيديو: {video['path']}", e)

            # الانتظار قبل الفيديو التالي
            await asyncio.sleep(video["interval"])

# ================== MAIN ==================
if __name__ == "__main__":
    asyncio.run(send_videos_forever())
