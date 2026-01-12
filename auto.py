import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError

# ================== CONFIG ==================
BOT_TOKEN = "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ"  # ضع توكن البوت الحقيقي هنا
CHAT_ID = "6968612778"  # ضع chat_id الخاص بك هنا
VIDEOS_DIR = "videos"
SEND_INTERVAL = 10  # ثانية
# ============================================

bot = Bot(token=BOT_TOKEN)

def get_videos():
    """
    يقرأ كل ملفات الفيديو في مجلد videos
    """
    files = []
    for f in os.listdir(VIDEOS_DIR):
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
            path = os.path.join(VIDEOS_DIR, f)
            caption = os.path.splitext(f)[0]  # اسم الملف بدون الامتداد ككابشن
            files.append({"path": path, "caption": caption})
    return sorted(files)  # يمكنك استخدام random.shuffle(files) إذا تحب ترتيب عشوائي

async def send_videos_forever():
    while True:
        videos = get_videos()
        if not videos:
            print("لا توجد فيديوهات في المجلد.")
            await asyncio.sleep(10)
            continue

        for video in videos:
            try:
                with open(video["path"], "rb") as v:
                    await bot.send_video(
                        chat_id=CHAT_ID,
                        video=v,
                        caption=video["caption"]
                    )
                print(f"تم إرسال الفيديو: {video['path']} مع الكابشن: {video['caption']}")
            except TelegramError as e:
                print(f"خطأ أثناء إرسال الفيديو: {video['path']}", e)

            await asyncio.sleep(SEND_INTERVAL)

# ================== MAIN ==================
if __name__ == "__main__":
    asyncio.run(send_videos_forever())
