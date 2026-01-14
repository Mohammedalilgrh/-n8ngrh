import subprocess
import sys

# تثبيت المكتبات تلقائيًا
def install_packages():
    packages = ['flask', 'python-telegram-bot', 'requests', 'werkzeug']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

install_packages()

# ثم استمر في باقي imports
from flask import Flask, jsonify, request, Response
from werkzeug.utils import secure_filename
import os
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from telegram import Bot, Update, InputMediaVideo, error as telegram_error
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading
import requests
import mimetypes
import hashlib
from typing import Dict, List, Any, Optional
import queue
import uuid

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8212401543:AAFZNuyv5Ua17hnJG4XHdB5JuRwZVCwJPCM")
CHAT_ID = os.getenv("CHAT_ID", "6968612778")
PORT = int(os.environ.get('PORT', 10000))

# إعدادات المسارات والملفات
VIDEOS_DIR = "videos"
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv'}
SEND_INTERVAL = 300  # 5 دقائق

# ملفات النظام
STATE_FILE = "state.json"
MESSAGES_DB = "messages_db.json"
LOG_FILE = "bot.log"

# إنشاء المجلدات اللازمة
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== FLASK APP ==================
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# ================== STATE MANAGEMENT ==================
class StateManager:
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.state = self.load_state()
    
    def load_state(self) -> Dict:
        """تحميل حالة النظام"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        
        return {
            "last_sent_index": -1,
            "videos_list": [],
            "last_sent_time": None,
            "sent_count": 0,
            "failed_count": 0,
            "n8n_messages": {}
        }
    
    def save_state(self):
        """حفظ حالة النظام"""
        try:
            self.state["updated_at"] = datetime.now().isoformat()
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def update_n8n_message(self, message_id: str, data: Dict):
        """تحديث رسالة n8n"""
        if "n8n_messages" not in self.state:
            self.state["n8n_messages"] = {}
        
        self.state["n8n_messages"][message_id] = {
            **data,
            "created_at": datetime.now().isoformat()
        }
        self.save_state()
    
    def get_n8n_message(self, message_id: str) -> Optional[Dict]:
        """الحصول على رسالة n8n"""
        return self.state.get("n8n_messages", {}).get(message_id)

# تهيئة StateManager
state_manager = StateManager()

# ================== VIDEO MANAGER ==================
class VideoManager:
    def __init__(self, videos_dir: str = VIDEOS_DIR):
        self.videos_dir = videos_dir
        self._ensure_directory()
    
    def _ensure_directory(self):
        """التأكد من وجود مجلد الفيديوهات"""
        os.makedirs(self.videos_dir, exist_ok=True)
    
    def scan_videos(self) -> List[Dict]:
        """فحص الفيديوهات في المجلد"""
        try:
            videos = []
            
            for filename in os.listdir(self.videos_dir):
                if any(filename.lower().endswith(f'.{ext}') for ext in ALLOWED_EXTENSIONS):
                    filepath = os.path.join(self.videos_dir, filename)
                    if os.path.isfile(filepath):
                        try:
                            file_size = os.path.getsize(filepath)
                            file_hash = self._get_file_hash(filepath)
                            
                            videos.append({
                                "id": file_hash[:16],  # استخدام جزء من الهاش كمعرف
                                "path": filepath,
                                "filename": filename,
                                "name": os.path.splitext(filename)[0],
                                "extension": os.path.splitext(filename)[1][1:].lower(),
                                "size": file_size,
                                "size_mb": file_size / (1024 * 1024),
                                "created_at": os.path.getctime(filepath),
                                "hash": file_hash,
                                "status": "pending"
                            })
                        except Exception as e:
                            logger.error(f"Error processing {filename}: {e}")
            
            # ترتيب أبجدي
            videos.sort(key=lambda x: x["filename"].lower())
            
            if videos:
                total_size = sum(v["size_mb"] for v in videos)
                logger.info(f"📊 Found {len(videos)} videos ({total_size:.2f} MB)")
            
            return videos
            
        except Exception as e:
            logger.error(f"Error scanning videos: {e}")
            return []
    
    def _get_file_hash(self, filepath: str) -> str:
        """حساب الهاش للملف"""
        try:
            hash_md5 = hashlib.md5()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return str(os.path.getsize(filepath))
    
    def get_video_info(self, video_id: str) -> Optional[Dict]:
        """الحصول على معلومات فيديو محدد"""
        videos = self.scan_videos()
        for video in videos:
            if video["id"] == video_id:
                return video
        return None

# تهيئة VideoManager
video_manager = VideoManager()

# ================== BOT MANAGER ==================
class BotManager:
    def __init__(self, token: str):
        self.token = token
        self.bot = None
        self.application = None
        self.n8n_queue = queue.Queue()
        self._initialize()
    
    def _initialize(self):
        """تهيئة البوت"""
        if not self.token:
            raise ValueError("BOT_TOKEN is required")
    
    async def start(self):
        """بدء تشغيل البوت"""
        try:
            self.application = Application.builder().token(self.token).build()
            self.bot = self.application.bot
            
            # إضافة handlers للأوامر
            self.application.add_handler(CommandHandler("start", self._start_command))
            self.application.add_handler(CommandHandler("help", self._help_command))
            self.application.add_handler(CommandHandler("status", self._status_command))
            self.application.add_handler(CommandHandler("list", self._list_command))
            self.application.add_handler(CommandHandler("send", self._send_command))
            self.application.add_handler(CommandHandler("next", self._next_command))
            
            # الحصول على معلومات البوت
            bot_info = await self.bot.get_me()
            logger.info(f"✅ Bot connected: @{bot_info.username} (ID: {bot_info.id})")
            
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect bot: {e}")
            raise
    
    async def _start_command(self, update: Update, context: CallbackContext):
        """معالج أمر /start"""
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hello {user.first_name}!\n\n"
            f"🤖 I'm Video Bot - Advanced Version\n"
            f"📁 Videos: {len(video_manager.scan_videos())}\n"
            f"⏱️ Interval: {SEND_INTERVAL // 60} minutes\n\n"
            f"📋 Commands:\n"
            f"/help - Show all commands\n"
            f"/status - Show bot status\n"
            f"/list - List all videos\n"
            f"/send <index> - Send specific video\n"
            f"/next - Send next video immediately"
        )
    
    async def _help_command(self, update: Update, context: CallbackContext):
        """معالج أمر /help"""
        await update.message.reply_text(
            "📋 **Available Commands:**\n\n"
            "/start - Start the bot\n"
            "/status - Show current status\n"
            "/list - List all videos in queue\n"
            "/send <number> - Send specific video by index\n"
            "/next - Send next video immediately\n"
            "/help - Show this help message\n\n"
            "🌐 **Web Endpoints:**\n"
            "/api/videos - Get videos list (JSON)\n"
            "/api/status - Get bot status (JSON)\n"
            "/api/send - Manually trigger video sending"
        )
    
    async def _status_command(self, update: Update, context: CallbackContext):
        """معالج أمر /status"""
        state = state_manager.state
        videos = video_manager.scan_videos()
        
        last_sent = state.get("last_sent_time")
        if last_sent:
            last_time = datetime.fromisoformat(last_sent)
            time_diff = datetime.now() - last_time
            last_sent_str = f"{time_diff.total_seconds() // 60:.0f} minutes ago"
        else:
            last_sent_str = "Never"
        
        status_text = (
            f"📊 **Bot Status**\n\n"
            f"✅ Status: **Running**\n"
            f"📁 Videos in queue: **{len(videos)}**\n"
            f"📤 Sent count: **{state.get('sent_count', 0)}**\n"
            f"❌ Failed count: **{state.get('failed_count', 0)}**\n"
            f"🕐 Last sent: **{last_sent_str}**\n"
            f"⏱️ Next in: **{SEND_INTERVAL // 60} minutes**\n\n"
            f"🔗 API: http://localhost:{PORT}/api/status"
        )
        
        await update.message.reply_text(status_text)
    
    async def _list_command(self, update: Update, context: CallbackContext):
        """معالج أمر /list"""
        videos = video_manager.scan_videos()
        
        if not videos:
            await update.message.reply_text("📭 No videos found in the queue.")
            return
        
        response = []
        for i, video in enumerate(videos[:10]):  # عرض أول 10 فيديوهات فقط
            size_mb = video["size_mb"]
            response.append(f"{i+1}. {video['filename']} ({size_mb:.1f} MB)")
        
        text = "📋 **Videos in Queue:**\n\n" + "\n".join(response)
        if len(videos) > 10:
            text += f"\n\n... and {len(videos) - 10} more videos"
        
        await update.message.reply_text(text)
    
    async def _send_command(self, update: Update, context: CallbackContext):
        """معالج أمر /send"""
        if not context.args:
            await update.message.reply_text("⚠️ Please specify video number: /send <number>")
            return
        
        try:
            index = int(context.args[0]) - 1
            videos = video_manager.scan_videos()
            
            if index < 0 or index >= len(videos):
                await update.message.reply_text(f"❌ Invalid number. Please use 1-{len(videos)}")
                return
            
            video = videos[index]
            await update.message.reply_text(f"📤 Sending video {index+1}: {video['filename']}")
            
            # إرسال الفيديو
            success = await self.send_video_with_n8n(video)
            
            if success:
                await update.message.reply_text("✅ Video sent successfully to all destinations!")
            else:
                await update.message.reply_text("❌ Failed to send video. Check logs for details.")
                
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number")
        except Exception as e:
            logger.error(f"Error in send command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def _next_command(self, update: Update, context: CallbackContext):
        """معالج أمر /next"""
        await update.message.reply_text("⏳ Sending next video...")
        
        # الحصول على الفيديو التالي
        videos = video_manager.scan_videos()
        if not videos:
            await update.message.reply_text("📭 No videos in queue")
            return
        
        state = state_manager.state
        next_index = (state.get("last_sent_index", -1) + 1) % len(videos)
        video = videos[next_index]
        
        # إرسال الفيديو
        success = await self.send_video_with_n8n(video)
        
        if success:
            state_manager.state["last_sent_index"] = next_index
            state_manager.state["last_sent_time"] = datetime.now().isoformat()
            state_manager.state["sent_count"] = state_manager.state.get("sent_count", 0) + 1
            state_manager.save_state()
            
            await update.message.reply_text(
                f"✅ Video sent successfully!\n\n"
                f"📹 {video['filename']}\n"
                f"📊 Next video in {SEND_INTERVAL // 60} minutes"
            )
        else:
            state_manager.state["failed_count"] = state_manager.state.get("failed_count", 0) + 1
            state_manager.save_state()
            await update.message.reply_text("❌ Failed to send video")
    
    async def send_video_with_n8n(self, video: Dict) -> bool:
        """إرسال الفيديو مع دعم n8n"""
        try:
            logger.info(f"📤 Sending video: {video['filename']}")
            
            # =========================
            # 1️⃣ إرسال إلى الخاص (CHAT_ID)
            # =========================
            logger.info(f"📤 Sending to private chat: {video['filename']}")
            with open(video["path"], "rb") as f:
                await self.bot.send_video(
                    chat_id=CHAT_ID,
                    video=f,
                    caption=video["name"],
                    supports_streaming=True,
                    parse_mode="HTML"
                )
            
            await asyncio.sleep(2)
            
            # =========================
            # 2️⃣ إرسال إلى القناة
            # =========================
            CHANNEL_ID = -1003218943676
            
            logger.info(f"📤 Sending to channel: {video['filename']}")
            with open(video["path"], "rb") as f:
                channel_message = await self.bot.send_video(
                    chat_id=CHANNEL_ID,
                    video=f,
                    caption=video["name"],
                    supports_streaming=True,
                    parse_mode="HTML"
                )
            
            # الحصول على file_id من الرسالة المرسلة للقناة
            file_id = channel_message.video.file_id
            logger.info(f"🆔 FILE_ID from channel: {file_id}")
            
            await asyncio.sleep(2)
            
            # =========================
            # 3️⃣ إرسال إلى البوت نفسه (للاستخدام في n8n)
            # =========================
            logger.info("🤖 Sending to bot itself (for n8n workflow)")
            
            # إنشاء رسالة خاصة للبوت
            message_to_bot = await self.bot.send_video(
                chat_id=6968612778,  # إرسال للبوت نفسه
                video=file_id,       # استخدام file_id من القناة
                caption=video["name"],
                supports_streaming=True,
                parse_mode="HTML"
            )
            
            # تخزين معلومات الرسالة للاستخدام في n8n
            message_id = str(message_to_bot.message_id)
            n8n_data = {
                "message_id": message_id,
                "video_info": {
                    "id": video["id"],
                    "filename": video["filename"],
                    "name": video["name"],
                    "size_mb": video["size_mb"],
                    "hash": video["hash"]
                },
                "file_id": file_id,
                "chat_id": 6968612778,
                "sent_at": datetime.now().isoformat(),
                "destinations": ["private_chat", "channel", "n8n_bot"],
                "status": "sent"
            }
            
            # حفظ الرسالة في قاعدة البيانات
            state_manager.update_n8n_message(message_id, n8n_data)
            
            # وضع البيانات في الـ queue للاستهلاك من خلال API
            self.n8n_queue.put({
                "type": "video_sent",
                "data": n8n_data,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"✅ Video sent to bot itself. Message ID: {message_id}")
            return True
            
        except telegram_error.RetryAfter as e:
            logger.warning(f"⏳ Flood control, waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after)
            return False
            
        except Exception as e:
            logger.error(f"❌ Error sending video: {e}")
            return False
    
    def get_n8n_message(self, message_id: str) -> Optional[Dict]:
        """الحصول على رسالة n8n"""
        return state_manager.get_n8n_message(message_id)
    
    def get_n8n_queue(self) -> queue.Queue:
        """الحصول على الـ queue الخاص بـ n8n"""
        return self.n8n_queue

# ================== FLASK ROUTES ==================
@app.route('/')
def home():
    """الصفحة الرئيسية"""
    videos = video_manager.scan_videos()
    state = state_manager.state
    
    return jsonify({
        "status": "running",
        "service": "Telegram Video Bot Pro",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "stats": {
            "videos_count": len(videos),
            "sent_count": state.get("sent_count", 0),
            "failed_count": state.get("failed_count", 0),
            "n8n_messages": len(state.get("n8n_messages", {}))
        },
        "endpoints": {
            "api_status": f"/api/status",
            "api_videos": f"/api/videos",
            "api_n8n": f"/api/n8n/messages",
            "api_send": f"/api/send",
            "api_next": f"/api/next",
            "health": f"/health",
            "docs": f"/api/docs"
        }
    })

@app.route('/health')
def health():
    """فحص صحة الخدمة"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/status', methods=['GET'])
def api_status():
    """الحصول على حالة البوت"""
    state = state_manager.state
    videos = video_manager.scan_videos()
    
    last_sent = state.get("last_sent_time")
    if last_sent:
        last_time = datetime.fromisoformat(last_sent)
        time_diff = datetime.now() - last_time
        minutes_ago = time_diff.total_seconds() / 60
    else:
        minutes_ago = None
    
    return jsonify({
        "bot": {
            "status": "running",
            "chat_id": CHAT_ID,
            "interval_seconds": SEND_INTERVAL,
            "interval_minutes": SEND_INTERVAL / 60
        },
        "queue": {
            "total_videos": len(videos),
            "next_index": (state.get("last_sent_index", -1) + 1) % max(len(videos), 1),
            "last_sent_minutes_ago": minutes_ago
        },
        "statistics": {
            "sent_count": state.get("sent_count", 0),
            "failed_count": state.get("failed_count", 0),
            "n8n_messages_stored": len(state.get("n8n_messages", {}))
        },
        "next_video": {
            "in_seconds": SEND_INTERVAL,
            "at": (datetime.now() + timedelta(seconds=SEND_INTERVAL)).isoformat()
        }
    })

@app.route('/api/videos', methods=['GET'])
def api_videos():
    """الحصول على قائمة الفيديوهات"""
    videos = video_manager.scan_videos()
    state = state_manager.state
    
    return jsonify({
        "count": len(videos),
        "next_index": state.get("last_sent_index", -1) + 1,
        "videos": videos
    })

@app.route('/api/videos/<video_id>', methods=['GET'])
def api_video_detail(video_id):
    """الحصول على تفاصيل فيديو محدد"""
    video = video_manager.get_video_info(video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    return jsonify(video)

@app.route('/api/send', methods=['POST'])
def api_send_video():
    """إرسال فيديو محدد أو التالي في القائمة"""
    data = request.get_json(silent=True) or {}
    
    # تحديد الفهرس المطلوب
    if data.get("index") is not None:
        try:
            index = int(data["index"])
            videos = video_manager.scan_videos()
            
            if index < 0 or index >= len(videos):
                return jsonify({"error": f"Invalid index. Use 0-{len(videos)-1}"}), 400
            
            video = videos[index]
            video_index = index
        except ValueError:
            return jsonify({"error": "Invalid index format"}), 400
    else:
        # إرسال الفيديو التالي
        videos = video_manager.scan_videos()
        if not videos:
            return jsonify({"error": "No videos in queue"}), 400
        
        state = state_manager.state
        video_index = (state.get("last_sent_index", -1) + 1) % len(videos)
        video = videos[video_index]
    
    # محاولة إرسال الفيديو
    try:
        if not bot_manager.bot:
            return jsonify({"error": "Bot not initialized"}), 500
        
        # تشغيل إرسال الفيديو
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(bot_manager.send_video_with_n8n(video))
        
        if success:
            # تحديث الحالة
            state_manager.state["last_sent_index"] = video_index
            state_manager.state["last_sent_time"] = datetime.now().isoformat()
            state_manager.state["sent_count"] = state_manager.state.get("sent_count", 0) + 1
            state_manager.save_state()
            
            return jsonify({
                "success": True,
                "message": "Video sent successfully",
                "video": {
                    "index": video_index,
                    "filename": video["filename"],
                    "name": video["name"]
                },
                "next_video_in": SEND_INTERVAL
            })
        else:
            state_manager.state["failed_count"] = state_manager.state.get("failed_count", 0) + 1
            state_manager.save_state()
            return jsonify({"error": "Failed to send video"}), 500
            
    except Exception as e:
        logger.error(f"API send error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/next', methods=['POST', 'GET'])
def api_send_next():
    """إرسال الفيديو التالي فوراً"""
    return api_send_video()

@app.route('/api/n8n/messages', methods=['GET'])
def api_n8n_messages():
    """الحصول على رسائل n8n"""
    state = state_manager.state
    messages = state.get("n8n_messages", {})
    
    # تحويل إلى قائمة
    messages_list = [
        {
            "id": msg_id,
            **msg_data
        }
        for msg_id, msg_data in messages.items()
    ]
    
    # ترتيب حسب الوقت
    messages_list.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
    
    return jsonify({
        "count": len(messages_list),
        "messages": messages_list[:100]  # إرجاع آخر 100 رسالة فقط
    })

@app.route('/api/n8n/latest', methods=['GET'])
def api_n8n_latest():
    """الحصول على أحدث رسالة لـ n8n"""
    state = state_manager.state
    messages = state.get("n8n_messages", {})
    
    if not messages:
        return jsonify({"error": "No messages available"}), 404
    
    # الحصول على أحدث رسالة
    latest_id = max(messages.keys(), key=lambda k: messages[k].get("sent_at", ""))
    latest_message = messages[latest_id]
    
    return jsonify({
        "message": latest_message,
        "metadata": {
            "id": latest_id,
            "is_latest": True
        }
    })

@app.route('/api/n8n/consume', methods=['GET'])
def api_n8n_consume():
    """استهلاك رسالة من queue n8n (للاستخدام في n8n workflows)"""
    try:
        n8n_queue = bot_manager.get_n8n_queue()
        
        if n8n_queue.empty():
            return jsonify({
                "available": False,
                "message": "No new messages in queue",
                "timestamp": datetime.now().isoformat()
            }), 200
        
        # الحصول على الرسالة من الـ queue
        message_data = n8n_queue.get_nowait()
        
        return jsonify({
            "available": True,
            "data": message_data,
            "consumed_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/n8n/webhook', methods=['POST'])
def api_n8n_webhook():
    """Webhook endpoint لاستقبال triggers من n8n"""
    data = request.get_json(silent=True) or {}
    
    # سجل البيانات الواردة
    logger.info(f"📥 Received webhook from n8n: {data}")
    
    # معالجة الطلب
    action = data.get("action", "next")
    
    if action == "send_next":
        # إرسال الفيديو التالي
        response = api_send_video()
        return response
    elif action == "get_status":
        return api_status()
    elif action == "get_videos":
        return api_videos()
    elif action == "get_latest":
        return api_n8n_latest()
    else:
        return jsonify({
            "received": True,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "message": "Webhook received but no action taken"
        })

@app.route('/api/docs', methods=['GET'])
def api_docs():
    """توثيق API"""
    docs = {
        "api_endpoints": {
            "GET /": "Home page with service info",
            "GET /health": "Health check endpoint",
            "GET /api/status": "Get bot status and statistics",
            "GET /api/videos": "List all videos in queue",
            "GET /api/videos/{id}": "Get specific video details",
            "POST /api/send": "Send video (use {'index': number} or send next)",
            "POST /api/next": "Send next video immediately",
            "GET /api/n8n/messages": "Get all n8n messages",
            "GET /api/n8n/latest": "Get latest n8n message",
            "GET /api/n8n/consume": "Consume n8n message from queue",
            "POST /api/n8n/webhook": "Webhook for n8n triggers"
        },
        "n8n_integration": {
            "workflow_triggers": [
                "Use webhook: POST to /api/n8n/webhook with {'action': 'send_next'}",
                "Poll endpoint: GET /api/n8n/consume every minute",
                "Get latest video: GET /api/n8n/latest"
            ],
            "message_format": {
                "type": "video_sent",
                "data": {
                    "message_id": "Telegram message ID",
                    "video_info": {
                        "id": "video_hash_id",
                        "filename": "original_filename.mp4",
                        "name": "video_name_without_extension",
                        "size_mb": 12.5,
                        "hash": "file_hash"
                    },
                    "file_id": "Telegram file_id",
                    "chat_id": 6968612778,
                    "sent_at": "ISO timestamp",
                    "destinations": ["private_chat", "channel", "n8n_bot"],
                    "status": "sent"
                }
            }
        },
        "telegram_bot": {
            "commands": [
                "/start - Start bot",
                "/help - Show help",
                "/status - Bot status",
                "/list - List videos",
                "/send <number> - Send specific video",
                "/next - Send next video"
            ]
        }
    }
    
    return jsonify(docs)

# ================== FILE UPLOAD ==================
def allowed_file(filename):
    """التحقق من صحة امتداد الملف"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """رفع فيديو جديد"""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(VIDEOS_DIR, filename)
        
        # حفظ الملف
        file.save(filepath)
        
        logger.info(f"📥 Uploaded new video: {filename}")
        
        return jsonify({
            "success": True,
            "message": "Video uploaded successfully",
            "filename": filename,
            "path": filepath,
            "size_bytes": os.path.getsize(filepath)
        })
    
    return jsonify({"error": "File type not allowed"}), 400

# ================== KEEP ALIVE ==================
def keep_alive():
    """البقاء نشطاً (لـ Render/Heroku)"""
    while True:
        try:
            response = requests.get(f"http://localhost:{PORT}/health")
            logger.info(f"🔄 Keep-alive ping: {response.status_code}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(300)  # كل 5 دقائق

# ================== MAIN LOOP ==================
async def main_loop():
    """الحلقة الرئيسية لإرسال الفيديوهات"""
    logger.info("🚀 Starting Telegram Video Bot Pro...")
    
    try:
        # تهيئة وإعداد البوت
        global bot_manager
        bot_manager = BotManager(BOT_TOKEN)
        await bot_manager.start()
        
        logger.info("✅ Bot initialized successfully")
        
        # عرض معلومات البدء
        videos = video_manager.scan_videos()
        logger.info(f"📁 Found {len(videos)} videos in queue")
        
        # بدء الحلقة الرئيسية
        while True:
            try:
                state = state_manager.state
                videos = video_manager.scan_videos()
                
                if not videos:
                    logger.info("📭 No videos in queue. Waiting...")
                    await asyncio.sleep(60)
                    continue
                
                # حساب الوقت للإرسال التالي
                last_sent = state.get("last_sent_time")
                if last_sent:
                    last_time = datetime.fromisoformat(last_sent)
                    time_since_last = (datetime.now() - last_time).total_seconds()
                    
                    if time_since_last < SEND_INTERVAL:
                        wait_time = SEND_INTERVAL - time_since_last
                        logger.info(f"⏳ Next video in {wait_time:.0f} seconds")
                        await asyncio.sleep(min(wait_time, 60))
                        continue
                
                # إرسال الفيديو التالي
                next_index = (state.get("last_sent_index", -1) + 1) % len(videos)
                video = videos[next_index]
                
                logger.info(f"🎬 Sending video ({next_index+1}/{len(videos)}): {video['filename']}")
                
                success = await bot_manager.send_video_with_n8n(video)
                
                if success:
                    state_manager.state["last_sent_index"] = next_index
                    state_manager.state["last_sent_time"] = datetime.now().isoformat()
                    state_manager.state["sent_count"] = state_manager.state.get("sent_count", 0) + 1
                    state_manager.save_state()
                    
                    logger.info(f"✅ Video sent successfully. Next in {SEND_INTERVAL} seconds")
                else:
                    state_manager.state["failed_count"] = state_manager.state.get("failed_count", 0) + 1
                    state_manager.save_state()
                    logger.error("❌ Failed to send video")
                
                await asyncio.sleep(SEND_INTERVAL)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                await asyncio.sleep(30)
                
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        raise

# ================== RUN FUNCTIONS ==================
def run_flask():
    """تشغيل Flask server"""
    logger.info(f"🌐 Starting Flask server on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_keep_alive():
    """تشغيل keep-alive"""
    logger.info("🔗 Starting keep-alive service")
    keep_alive()

# ================== ENTRY POINT ==================
if __name__ == "__main__":
    # طباعة معلومات البدء
    print("=" * 60)
    print("🤖 TELEGRAM VIDEO BOT PRO - ADVANCED VERSION")
    print("=" * 60)
    print(f"👤 Chat ID: {CHAT_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"⏰ Interval: {SEND_INTERVAL} seconds ({SEND_INTERVAL/60:.1f} minutes)")
    print(f"🌐 Port: {PORT}")
    print(f"🤖 N8N Bot ID: 6968612778")
    print(f"📊 API Status: http://localhost:{PORT}/api/status")
    print("=" * 60)
    
    # إنشاء threads
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    
    # بدء threads
    flask_thread.start()
    keep_alive_thread.start()
    
    # تشغيل البوت
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
