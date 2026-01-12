import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError

# ================== CONFIG ==================
BOT_TOKEN = "8212401543:AAHbG82cYrrLZb3Rk33jpGWCKR9r6_mpYTQ"  # ضع توكن البوت الحقيقي هنا
CHAT_ID = 6968612778  # chat id الخاص بك
VIDEOS_DIR = "videos"
SEND_INTERVAL = 10  # ثانية بين كل فيديو
# ============================================

bot = Bot(token=BOT_TOKEN)

# قائمة لحفظ الفيديوهات المكتشفة
known_videos = set()

def scan_videos():
    """
    يقرأ كل ملفات الفيديو في مجلد videos ويضيفها لقائمة known_videos
    """
    if not os.path.exists(VIDEOS_DIR):
        os.makedirs(VIDEOS_DIR)
        print(f"تم إنشاء المجلد {VIDEOS_DIR}. ضع الفيديوهات داخله.")
        return []

    current_videos = []
    for f in os.listdir(VIDEOS_DIR):
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
            if f not in known_videos:
                known_videos.add(f)
            path = os.path.join(VIDEOS_DIR, f)
            caption = os.path.splitext(f)[0]  # اسم الملف بدون الامتداد ككابشن
            current_videos.append({"path": path, "caption": caption})
    return sorted(current_videos)

async def send_videos_forever():
    """
    إرسال الفيديوهات باستمرار بشكل لانهائي
    """
    while True:
        videos = scan_videos()
        if not videos:
            print("لا توجد فيديوهات في المجلد.")
            await asyncio.sleep(5)
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

        # بعد إرسال كل الفيديوهات الحالية، سيعيد قراءة أي فيديوهات جديدة تلقائيًا

# ================== MAIN ==================
if __name__ == "__main__":
    asyncio.run(send_videos_forever())
