import subprocess
import sys
import os

# تثبيت المكتبات تلقائيًا
def install_packages():
    packages = ['flask', 'python-telegram-bot', 'requests', 'flask-cors']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

install_packages()

# ================== IMPORTS ==================
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import asyncio
import json
import logging
import time
from datetime import datetime
from telegram import Bot, Update, InputFile
from telegram.ext import Application, MessageHandler, filters, CallbackContext
import threading
import requests
from urllib.parse import quote
import uuid

# ================== CONFIG ==================
PORT = int(os.environ.get('PORT', 10000))
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAHfBzcnW1u2XFBSllTFoJlqOKcK3rIUhxU")
CHAT_ID = os.getenv("CHAT_ID", "-1003218943676")  # معرف القناة/الجروب
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")  # URL العام للتطبيق

VIDEOS_DIR = "videos"
DATABASE_FILE = "videos_db.json"
LOG_FILE = "video_bot.log"

# ================== FLASK APP ==================
app = Flask(__name__)
CORS(app)  # تفعيل CORS للسماح لـ Zapier بالوصول

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

# ================== DATABASE ==================
class VideoDatabase:
    def __init__(self, db_file=DATABASE_FILE):
        self.db_file = db_file
        self.videos_dir = VIDEOS_DIR
        os.makedirs(self.videos_dir, exist_ok=True)
        self.load()
    
    def load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = {"videos": [], "last_id": 0}
        else:
            self.data = {"videos": [], "last_id": 0}
        return self.data
    
    def save(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add_video(self, video_info):
        video_id = str(uuid.uuid4())
        video_info['id'] = video_id
        video_info['created_at'] = datetime.now().isoformat()
        video_info['public_url'] = f"{BASE_URL}/video/{video_id}"
        video_info['download_url'] = f"{BASE_URL}/download/{video_id}"
        
        self.data["videos"].append(video_info)
        self.save()
        
        logger.info(f"✅ تم إضافة فيديو جديد: {video_info['filename']} - ID: {video_id}")
        return video_info
    
    def get_video(self, video_id):
        for video in self.data["videos"]:
            if video.get('id') == video_id:
                return video
        return None
    
    def get_all_videos(self):
        return self.data["videos"]
    
    def get_latest_videos(self, limit=10):
        videos = sorted(self.data["videos"], 
                       key=lambda x: x.get('created_at', ''), 
                       reverse=True)
        return videos[:limit]

# إنشاء كائن قاعدة البيانات
db = VideoDatabase()

# ================== FLASK ROUTES ==================
@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "service": "SaveVideoBot - Video Saver with Public URLs",
        "endpoints": {
            "all_videos": "/api/videos",
            "latest_videos": "/api/videos/latest",
            "video_info": "/api/video/<id>",
            "video_file": "/video/<id>",
            "video_download": "/download/<id>",
            "health": "/health"
        },
        "timestamp": datetime.now().isoformat(),
        "total_videos": len(db.get_all_videos())
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/api/videos')
def api_all_videos():
    """API للحصول على جميع الفيديوهات (للاستخدام مع Zapier)"""
    videos = db.get_all_videos()
    return jsonify({
        "count": len(videos),
        "videos": videos
    })

@app.route('/api/videos/latest')
def api_latest_videos():
    """API للحصول على أحدث الفيديوهات"""
    limit = request.args.get('limit', 10, type=int)
    videos = db.get_latest_videos(limit)
    return jsonify({
        "count": len(videos),
        "limit": limit,
        "videos": videos
    })

@app.route('/api/video/<video_id>')
def api_video_info(video_id):
    """API للحصول على معلومات فيديو معين"""
    video = db.get_video(video_id)
    if video:
        return jsonify(video)
    return jsonify({"error": "Video not found"}), 404

@app.route('/video/<video_id>')
def serve_video(video_id):
    """تقديم الفيديو للعرض في المتصفح"""
    video = db.get_video(video_id)
    if not video or not os.path.exists(video.get('filepath')):
        return "Video not found", 404
    
    # إرسال الفيديو مع إمكانية التدفق (streaming)
    return send_from_directory(
        os.path.dirname(video['filepath']),
        os.path.basename(video['filepath']),
        as_attachment=False,
        mimetype='video/mp4'
    )

@app.route('/download/<video_id>')
def download_video(video_id):
    """تحميل الفيديو"""
    video = db.get_video(video_id)
    if not video or not os.path.exists(video.get('filepath')):
        return "Video not found", 404
    
    return send_from_directory(
        os.path.dirname(video['filepath']),
        os.path.basename(video['filepath']),
        as_attachment=True,
        download_name=video['filename']
    )

@app.route('/videos')
def videos_page():
    """صفحة ويب لعرض جميع الفيديوهات"""
    videos = db.get_all_videos()
    html = """
    <!DOCTYPE html>
    <html lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SaveVideoBot - جميع الفيديوهات</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                direction: rtl;
                text-align: right;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 30px;
            }
            .video-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
            }
            .video-card {
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }
            .video-card:hover {
                transform: translateY(-5px);
            }
            .video-thumbnail {
                width: 100%;
                height: 200px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 48px;
            }
            .video-info {
                padding: 20px;
            }
            .video-title {
                font-weight: bold;
                margin-bottom: 10px;
                color: #333;
            }
            .video-date {
                color: #666;
                font-size: 12px;
                margin-bottom: 15px;
            }
            .video-links {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            .btn {
                padding: 8px 15px;
                border-radius: 5px;
                text-decoration: none;
                color: white;
                font-size: 14px;
                flex: 1;
                text-align: center;
            }
            .btn-view {
                background: #4CAF50;
            }
            .btn-download {
                background: #2196F3;
            }
            .btn-api {
                background: #FF9800;
            }
            .stats {
                background: white;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📹 SaveVideoBot</h1>
                <p>جميع الفيديوهات المحفوظة - روابط عامة للجميع</p>
            </div>
            
            <div class="stats">
                <h3>📊 الإحصائيات</h3>
                <p>إجمالي الفيديوهات: <strong>""" + str(len(videos)) + """</strong></p>
                <p>📎 رابط API للاستخدام مع Zapier: <code>""" + BASE_URL + """/api/videos</code></p>
            </div>
            
            <div class="video-grid">
    """
    
    for video in reversed(videos):  # عرض أحدث الفيديوهات أولاً
        html += f"""
                <div class="video-card">
                    <div class="video-thumbnail">
                        <span>🎬</span>
                    </div>
                    <div class="video-info">
                        <div class="video-title">{video.get('caption', 'بدون عنوان')}</div>
                        <div class="video-date">📅 {video.get('created_at', '')}</div>
                        <div class="video-size">📦 {video.get('size_mb', 0):.1f} MB</div>
                        <div class="video-links">
                            <a href="{video.get('public_url')}" class="btn btn-view" target="_blank">👁️ مشاهدة</a>
                            <a href="{video.get('download_url')}" class="btn btn-download" target="_blank">📥 تحميل</a>
                        </div>
                    </div>
                </div>
        """
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    return html

# ================== TELEGRAM BOT ==================
async def save_telegram_video(video_file, caption, message_id, chat_id):
    """حفظ فيديو من تلغرام"""
    try:
        # إنشاء اسم فريد للملف
        timestamp = int(time.time())
        filename = f"video_{timestamp}_{message_id}.mp4"
        filepath = os.path.join(VIDEOS_DIR, filename)
        
        # تحميل الفيديو من تلغرام
        bot = Bot(token=BOT_TOKEN)
        
        # الحصول على معلومات الملف
        file_info = await bot.get_file(video_file.file_id)
        
        # تحميل الملف
        await file_info.download_to_drive(filepath)
        
        # حساب حجم الملف
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)
        
        # إعداد معلومات الفيديو
        video_info = {
            'filename': filename,
            'filepath': filepath,
            'caption': caption or "بدون عنوان",
            'original_caption': caption,
            'telegram_file_id': video_file.file_id,
            'message_id': message_id,
            'chat_id': chat_id,
            'file_size': file_size,
            'size_mb': size_mb,
            'mime_type': video_file.mime_type or 'video/mp4'
        }
        
        # حفظ في قاعدة البيانات
        saved_video = db.add_video(video_info)
        
        logger.info(f"✅ تم حفظ فيديو: {filename} ({size_mb:.1f} MB)")
        return saved_video
        
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ الفيديو: {e}")
        return None

async def handle_video_message(update: Update, context: CallbackContext):
    """معالجة الرسائل التي تحتوي على فيديو"""
    try:
        message = update.effective_message
        
        # التحقق إذا كانت القناة/الجروب المطلوبة
        if str(message.chat_id) != CHAT_ID:
            return
        
        # التحقق من وجود فيديو
        if message.video:
            video_file = message.video
            caption = message.caption or ""
            
            # إعلام ببدء الحفظ
            processing_msg = await message.reply_text("📥 جاري حفظ الفيديو وجرين الرابط العام...")
            
            # حفظ الفيديو
            saved_video = await save_telegram_video(video_file, caption, message.message_id, message.chat_id)
            
            if saved_video:
                # إرسال الرابط العام في القناة
                public_url = saved_video['public_url']
                download_url = saved_video['download_url']
                
                reply_text = f"""
✅ **تم حفظ الفيديو بنجاح!**

📝 **العنوان:** {saved_video['caption']}
📦 **الحجم:** {saved_video['size_mb']:.1f} MB

🔗 **الروابط العامة:**
👁️ **مشاهدة مباشرة:** {public_url}
📥 **تحميل مباشر:** {download_url}

📎 **للاستخدام مع Zapier:**
• API Link: {BASE_URL}/api/videos
• Latest Videos: {BASE_URL}/api/videos/latest
• هذا الفيديو: {BASE_URL}/api/video/{saved_video['id']}

🆔 **معرف الفيديو:** `{saved_video['id']}`
                """
                
                await processing_msg.delete()
                await message.reply_text(reply_text, disable_web_page_preview=False)
                
                logger.info(f"📤 تم نشر الروابط العامة للفيديو: {saved_video['filename']}")
            else:
                await processing_msg.edit_text("❌ فشل في حفظ الفيديو")
                
        # معالجة الفيديوهات في الوسائط المتعددة
        elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
            video_file = message.document
            caption = message.caption or ""
            
            processing_msg = await message.reply_text("📥 جاري حفظ الفيديو (ملف) وجرين الرابط العام...")
            
            saved_video = await save_telegram_video(video_file, caption, message.message_id, message.chat_id)
            
            if saved_video:
                public_url = saved_video['public_url']
                download_url = saved_video['download_url']
                
                reply_text = f"""
✅ **تم حفظ الفيديو (ملف) بنجاح!**

📝 **العنوان:** {saved_video['caption']}
📦 **الحجم:** {saved_video['size_mb']:.1f} MB

🔗 **الروابط العامة:**
👁️ **مشاهدة مباشرة:** {public_url}
📥 **تحميل مباشر:** {download_url}

🆔 **معرف الفيديو:** `{saved_video['id']}`
                """
                
                await processing_msg.delete()
                await message.reply_text(reply_text, disable_web_page_preview=False)
                
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الرسالة: {e}")
        try:
            await update.effective_message.reply_text(f"❌ حدث خطأ: {str(e)}")
        except:
            pass

async def handle_forwarded_message(update: Update, context: CallbackContext):
    """معالجة الرسائل المعاد توجيهها التي تحتوي على فيديو"""
    await handle_video_message(update, context)

async def start_bot():
    """تشغيل بوت تلغرام"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # إضافة handlers
        application.add_handler(MessageHandler(
            filters.VIDEO | (filters.Document.VIDEO & filters.Chat(chat_id=int(CHAT_ID))), 
            handle_video_message
        ))
        
        # handler للرسائل المعاد توجيهها
        application.add_handler(MessageHandler(
            filters.FORWARDED & (filters.VIDEO | (filters.Document.VIDEO & filters.Chat(chat_id=int(CHAT_ID)))), 
            handle_forwarded_message
        ))
        
        # بدء البوت
        await application.initialize()
        await application.start()
        
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot متصل: @{bot_info.username}")
        logger.info(f"📢 يراقب القناة/الجروب: {CHAT_ID}")
        
        # تشغيل حتى يتم إيقافه
        await application.updater.start_polling()
        await application.idle()
        
    except Exception as e:
        logger.error(f"❌ فشل في تشغيل البوت: {e}")

# ================== KEEP ALIVE FUNCTION ==================
def keep_alive():
    """Ping the app to keep it awake"""
    while True:
        try:
            if BASE_URL.startswith('http'):
                response = requests.get(f"{BASE_URL}/health")
                logger.info(f"🔄 Keep-alive ping: {response.status_code}")
            else:
                # إذا لم يتم تعيين BASE_URL، استخدم localhost
                response = requests.get(f"http://localhost:{PORT}/health")
                logger.info(f"🔄 Keep-alive ping (localhost): {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Keep-alive error: {e}")
        time.sleep(300)  # كل 5 دقائق

# ================== RUN FUNCTIONS ==================
def run_flask():
    """تشغيل Flask server"""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_telegram_bot():
    """تشغيل بوت تلغرام في thread منفصل"""
    asyncio.run(start_bot())

def run_keep_alive():
    """تشغيل keep-alive"""
    keep_alive()

if __name__ == "__main__":
    # طباعة معلومات البدء
    print("=" * 60)
    print("🤖 SaveVideoBot - Advanced Video Saver with Public URLs")
    print(f"📢 Channel/Group ID: {CHAT_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"🔗 Public Videos Page: {BASE_URL}/videos")
    print(f"📎 API for Zapier: {BASE_URL}/api/videos")
    print(f"📊 Total Videos: {len(db.get_all_videos())}")
    print("=" * 60)
    
    # إنشاء threads
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    
    # بدء threads
    flask_thread.start()
    keep_alive_thread.start()
    
    # تشغيل بوت تلغرام في thread رئيسي
    try:
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
```

## 📋 **متطلبات التشغيل**

### **1. متغيرات البيئة المطلوبة:**
```bash
BOT_TOKEN=رقم_توكن_البوت_هنا
CHAT_ID=-100xxxxxxxxxx  # معرف قناتك @n8ngroupgrh
BASE_URL=https://your-app.onrender.com  # أو أي رابط للتطبيق
```

### **2. كيفية الحصول على CHAT_ID:**
1. أضف البوت `@RawDataBot` إلى قناتك
2. أرسل أي رسالة في القناة
3. سيرسل لك البوت معرف القناة (رقم سالب مثل `-1003218943676`)

### **3. تكوين Zapier:**
1. في Zapier، أنشئ **Webhook Zap**
2. استخدم الرابط: `https://your-app.onrender.com/api/videos/latest`
3. سيحصل Zapier على أحدث الفيديوهات مع:
   - `public_url`: رابط المشاهدة المباشرة
   - `download_url`: رابط التحميل
   - `caption`: التسمية التوضيحية
   - `created_at`: وقت الإنشاء

### **4. ميزات البوت:**
✅ **حفظ تلقائي**: أي فيديو يرسل في القناة يحفظ تلقائياً  
✅ **روابط عامة**: كل فيديو له رابط مشاهدة وتحميل  
✅ **واجهة ويب**: صفحة لعرض جميع الفيديوهات  
✅ **API لـ Zapier**: نقاط نهاية RESTful للاستخدام مع Zapier  
✅ **معالجة الفيديوهات المعاد توجيهها**  
✅ **Keep-alive**: يمنع إيقاف التطبيق في Render  

### **5. نقاط API المتاحة:**
```
/                   ← صفحة الرئيسية
/videos             ← صفحة ويب لعرض جميع الفيديوهات
/api/videos         ← جميع الفيديوهات (JSON)
/api/videos/latest  ← أحدث 10 فيديوهات
/api/video/{id}     ← معلومات فيديو محدد
/video/{id}         ← مشاهدة الفيديو
/download/{id}      ← تحميل الفيديو
/health             ← حالة التطبيق
```

### **6. مثال لاستجابة API (لـ Zapier):**
```json
{
  "count": 5,
  "videos": [
    {
      "id": "uuid-here",
      "filename": "video_123456789.mp4",
      "caption": "عنوان الفيديو",
      "public_url": "https://your-app.onrender.com/video/uuid-here",
      "download_url": "https://your-app.onrender.com/download/uuid-here",
      "created_at": "2024-01-15T10:30:00",
      "size_mb": 15.5
    }
  ]
}
```

### **7. deployment على Render:**
1. انشئ ملف `requirements.txt`:
```txt
flask
python-telegram-bot
requests
flask-cors
```

2. انشئ ملف `render.yaml`:
```yaml
services:
  - type: web
    name: savevideobot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: CHAT_ID
        sync: false
      - key: BASE_URL
        fromService:
          name: savevideobot
          type: web
          property: url
```

3. انشر على Render وسيصبح لديك:
   - رابط تطبيق عام
   - كل فيديو في قناتك يحفظ ويولد له رابط
   - واجهة API لاستخدامها مع Zapier

البوت جاهز للاستخدام مباشرة! فقط عين متغيرات البيئة وابدأ الإرسال في قناتك.
