import subprocess
import sys
import os

# تثبيت المكتبات تلقائيًا
def install_packages():
    packages = ['flask', 'python-telegram-bot==20.7', 'requests', 'flask-cors']
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
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import threading
import requests
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
CORS(app)  # تفعيل CORS للسماح بالوصول من أي مصدر

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
    
    def search_videos(self, keyword):
        """بحث في الفيديوهات"""
        results = []
        keyword = keyword.lower()
        for video in self.data["videos"]:
            caption = video.get('caption', '').lower()
            if keyword in caption:
                results.append(video)
        return results

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
            "search_videos": "/api/videos/search?q=كلمة",
            "video_info": "/api/video/<id>",
            "video_file": "/video/<id>",
            "video_download": "/download/<id>",
            "videos_page": "/videos",
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
    """API للحصول على جميع الفيديوهات"""
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

@app.route('/api/videos/search')
def api_search_videos():
    """API للبحث في الفيديوهات"""
    keyword = request.args.get('q', '')
    if not keyword:
        return jsonify({"error": "يرجى إدخال كلمة للبحث"}), 400
    
    videos = db.search_videos(keyword)
    return jsonify({
        "count": len(videos),
        "keyword": keyword,
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
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                direction: rtl;
                text-align: right;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                min-height: 100vh;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px 30px;
                border-radius: 15px;
                margin-bottom: 40px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                text-align: center;
            }
            
            .header h1 {
                font-size: 2.8rem;
                margin-bottom: 15px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
            }
            
            .header p {
                font-size: 1.2rem;
                opacity: 0.9;
                max-width: 800px;
                margin: 0 auto;
            }
            
            .stats-card {
                background: white;
                padding: 25px;
                border-radius: 15px;
                margin-bottom: 30px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
            }
            
            .stat-item {
                text-align: center;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 10px;
                transition: transform 0.3s;
            }
            
            .stat-item:hover {
                transform: translateY(-5px);
                background: #e9ecef;
            }
            
            .stat-item h3 {
                color: #667eea;
                margin-bottom: 10px;
                font-size: 1.1rem;
            }
            
            .stat-item p {
                font-size: 2rem;
                font-weight: bold;
                color: #764ba2;
            }
            
            .search-box {
                background: white;
                padding: 25px;
                border-radius: 15px;
                margin-bottom: 30px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            
            .search-box input {
                width: 100%;
                padding: 15px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                font-size: 1.1rem;
                transition: border-color 0.3s;
            }
            
            .search-box input:focus {
                outline: none;
                border-color: #667eea;
            }
            
            .video-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 25px;
                margin-bottom: 50px;
            }
            
            .video-card {
                background: white;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .video-card:hover {
                transform: translateY(-10px) scale(1.02);
                box-shadow: 0 15px 35px rgba(0,0,0,0.15);
            }
            
            .video-thumbnail {
                width: 100%;
                height: 200px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                position: relative;
                overflow: hidden;
            }
            
            .video-thumbnail::before {
                content: '🎬';
                font-size: 70px;
                opacity: 0.8;
            }
            
            .video-info {
                padding: 25px;
                flex-grow: 1;
                display: flex;
                flex-direction: column;
            }
            
            .video-title {
                font-size: 1.3rem;
                font-weight: bold;
                margin-bottom: 15px;
                color: #2c3e50;
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            
            .video-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                font-size: 0.9rem;
                color: #666;
            }
            
            .video-date {
                display: flex;
                align-items: center;
                gap: 5px;
            }
            
            .video-size {
                display: flex;
                align-items: center;
                gap: 5px;
                background: #f0f0f0;
                padding: 5px 10px;
                border-radius: 20px;
            }
            
            .video-links {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: auto;
            }
            
            .btn {
                padding: 12px 20px;
                border-radius: 10px;
                text-decoration: none;
                color: white;
                font-weight: 600;
                text-align: center;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }
            
            .btn-view {
                background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%);
            }
            
            .btn-view:hover {
                background: linear-gradient(135deg, #45a049 0%, #1B5E20 100%);
                transform: translateY(-2px);
            }
            
            .btn-download {
                background: linear-gradient(135deg, #2196F3 0%, #0D47A1 100%);
            }
            
            .btn-download:hover {
                background: linear-gradient(135deg, #1E88E5 0%, #0D3C82 100%);
                transform: translateY(-2px);
            }
            
            .api-info {
                background: white;
                padding: 30px;
                border-radius: 15px;
                margin-top: 40px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            
            .api-info h3 {
                color: #667eea;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .api-endpoints {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            
            .api-endpoint {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }
            
            .endpoint-method {
                display: inline-block;
                padding: 5px 10px;
                background: #667eea;
                color: white;
                border-radius: 5px;
                font-size: 0.9rem;
                margin-bottom: 10px;
            }
            
            .endpoint-url {
                font-family: monospace;
                background: #e9ecef;
                padding: 10px;
                border-radius: 5px;
                word-break: break-all;
                margin-bottom: 10px;
            }
            
            .endpoint-desc {
                color: #666;
                font-size: 0.9rem;
            }
            
            .no-videos {
                text-align: center;
                padding: 50px;
                background: white;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                grid-column: 1 / -1;
            }
            
            .no-videos h3 {
                color: #667eea;
                margin-bottom: 20px;
                font-size: 1.5rem;
            }
            
            @media (max-width: 768px) {
                .header h1 {
                    font-size: 2rem;
                }
                
                .video-grid {
                    grid-template-columns: 1fr;
                }
                
                .stats-card {
                    grid-template-columns: 1fr;
                }
                
                .container {
                    padding: 10px;
                }
            }
            
            .badge {
                display: inline-block;
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: bold;
                margin-left: 10px;
            }
            
            .badge-new {
                background: #4CAF50;
                color: white;
            }
            
            .badge-popular {
                background: #FF9800;
                color: white;
            }
        </style>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    </head>
    <body>
        <div class="container">
            <!-- الهيدر -->
            <div class="header">
                <h1><i class="fas fa-video"></i> SaveVideoBot</h1>
                <p>نظام حفظ الفيديوهات من تلغرام وتوليد روابط عامة للمشاهدة والتحميل</p>
            </div>
            
            <!-- إحصائيات -->
            <div class="stats-card">
                <div class="stat-item">
                    <h3><i class="fas fa-film"></i> إجمالي الفيديوهات</h3>
                    <p>""" + str(len(videos)) + """</p>
                </div>
                <div class="stat-item">
                    <h3><i class="fas fa-server"></i> حالة الخادم</h3>
                    <p style="color: #4CAF50;"><i class="fas fa-circle"></i> نشط</p>
                </div>
                <div class="stat-item">
                    <h3><i class="fas fa-link"></i> رابط التطبيق</h3>
                    <p style="font-size: 1rem;">""" + BASE_URL + """</p>
                </div>
            </div>
            
            <!-- صندوق البحث -->
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 ابحث في الفيديوهات... (اضغط Enter للبحث)">
                <div id="searchResults" style="margin-top: 20px; display: none;"></div>
            </div>
            
            <!-- شبكة الفيديوهات -->
            <div class="video-grid" id="videoGrid">
    """
    
    if videos:
        # عرض أحدث الفيديوهات أولاً
        for i, video in enumerate(reversed(videos)):
            # حساب الوقت المنقضي
            created_at = video.get('created_at', '')
            time_ago = ""
            if created_at:
                try:
                    created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    now = datetime.now()
                    diff = now - created_date
                    
                    if diff.days > 0:
                        time_ago = f"منذ {diff.days} يوم"
                    elif diff.seconds // 3600 > 0:
                        time_ago = f"منذ {diff.seconds // 3600} ساعة"
                    else:
                        time_ago = f"منذ {diff.seconds // 60} دقيقة"
                except:
                    time_ago = created_at
            else:
                time_ago = "غير معروف"
            
            # إضافة badges
            badges = ""
            if i < 3:  # أول 3 فيديوهات تعتبر جديدة
                badges = '<span class="badge badge-new">جديد</span>'
            
            html += f"""
                <div class="video-card">
                    <div class="video-thumbnail">
                        {badges}
                    </div>
                    <div class="video-info">
                        <div class="video-title">
                            {video.get('caption', 'بدون عنوان')[:100]}
                            {'' if len(video.get('caption', '')) <= 100 else '...'}
                        </div>
                        <div class="video-meta">
                            <div class="video-date">
                                <i class="far fa-calendar"></i>
                                {time_ago}
                            </div>
                            <div class="video-size">
                                <i class="fas fa-weight-hanging"></i>
                                {video.get('size_mb', 0):.1f} MB
                            </div>
                        </div>
                        <div class="video-links">
                            <a href="{video.get('public_url')}" class="btn btn-view" target="_blank">
                                <i class="fas fa-eye"></i>
                                مشاهدة
                            </a>
                            <a href="{video.get('download_url')}" class="btn btn-download" target="_blank">
                                <i class="fas fa-download"></i>
                                تحميل
                            </a>
                        </div>
                    </div>
                </div>
            """
    else:
        html += """
            <div class="no-videos">
                <h3><i class="fas fa-film"></i> لا توجد فيديوهات حالياً</h3>
                <p>أرسل فيديوهات في قناتك على تلغرام وسيتم حفظها هنا تلقائياً</p>
            </div>
        """
    
    html += """
            </div>
            
            <!-- معلومات API -->
            <div class="api-info">
                <h3><i class="fas fa-code"></i> واجهة برمجة التطبيق (API)</h3>
                <p>يمكنك استخدام هذه النقاط للحصول على بيانات الفيديوهات برمجياً:</p>
                
                <div class="api-endpoints">
                    <div class="api-endpoint">
                        <span class="endpoint-method">GET</span>
                        <div class="endpoint-url">""" + BASE_URL + """/api/videos</div>
                        <div class="endpoint-desc">جميع الفيديوهات بتنسيق JSON</div>
                    </div>
                    
                    <div class="api-endpoint">
                        <span class="endpoint-method">GET</span>
                        <div class="endpoint-url">""" + BASE_URL + """/api/videos/latest?limit=10</div>
                        <div class="endpoint-desc">أحدث الفيديوهات (تحديد العدد بمعامل limit)</div>
                    </div>
                    
                    <div class="api-endpoint">
                        <span class="endpoint-method">GET</span>
                        <div class="endpoint-url">""" + BASE_URL + """/api/videos/search?q=كلمة</div>
                        <div class="endpoint-desc">البحث في الفيديوهات حسب الكلمة</div>
                    </div>
                    
                    <div class="api-endpoint">
                        <span class="endpoint-method">GET</span>
                        <div class="endpoint-url">""" + BASE_URL + """/api/video/{id}</div>
                        <div class="endpoint-desc">معلومات فيديو محدد حسب المعرف</div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // وظيفة البحث
            const searchInput = document.getElementById('searchInput');
            const videoGrid = document.getElementById('videoGrid');
            const searchResults = document.getElementById('searchResults');
            
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    const keyword = this.value.trim();
                    if (keyword) {
                        searchVideos(keyword);
                    } else {
                        // إذا كان البحث فارغاً، إعادة عرض كل الفيديوهات
                        fetch('/api/videos')
                            .then(response => response.json())
                            .then(data => {
                                updateVideoGrid(data.videos);
                                searchResults.style.display = 'none';
                                searchResults.innerHTML = '';
                            });
                    }
                }
            });
            
            function searchVideos(keyword) {
                fetch(`/api/videos/search?q=${encodeURIComponent(keyword)}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.videos.length > 0) {
                            updateVideoGrid(data.videos);
                            searchResults.style.display = 'block';
                            searchResults.innerHTML = `
                                <div style="background: #e3f2fd; padding: 15px; border-radius: 10px; border-right: 4px solid #2196F3;">
                                    <i class="fas fa-search"></i> 
                                    تم العثور على ${data.count} فيديو لكلمة "${keyword}"
                                </div>
                            `;
                        } else {
                            searchResults.style.display = 'block';
                            searchResults.innerHTML = `
                                <div style="background: #ffebee; padding: 15px; border-radius: 10px; border-right: 4px solid #f44336;">
                                    <i class="fas fa-exclamation-circle"></i> 
                                    لم يتم العثور على نتائج لكلمة "${keyword}"
                                </div>
                            `;
                        }
                    })
                    .catch(error => {
                        console.error('Error searching videos:', error);
                        searchResults.style.display = 'block';
                        searchResults.innerHTML = `
                            <div style="background: #fff3e0; padding: 15px; border-radius: 10px; border-right: 4px solid #ff9800;">
                                <i class="fas fa-exclamation-triangle"></i> 
                                حدث خطأ أثناء البحث
                            </div>
                        `;
                    });
            }
            
            function updateVideoGrid(videos) {
                let html = '';
                
                if (videos.length === 0) {
                    html = `
                        <div class="no-videos" style="grid-column: 1 / -1;">
                            <h3><i class="fas fa-film"></i> لا توجد فيديوهات</h3>
                        </div>
                    `;
                } else {
                    videos.forEach((video, index) => {
                        const created_at = video.created_at || '';
                        let time_ago = '';
                        
                        if (created_at) {
                            const createdDate = new Date(created_at);
                            const now = new Date();
                            const diff = now - createdDate;
                            
                            if (diff > 86400000) {
                                time_ago = `منذ ${Math.floor(diff / 86400000)} يوم`;
                            } else if (diff > 3600000) {
                                time_ago = `منذ ${Math.floor(diff / 3600000)} ساعة`;
                            } else {
                                time_ago = `منذ ${Math.floor(diff / 60000)} دقيقة`;
                            }
                        }
                        
                        let badges = '';
                        if (index < 3) {
                            badges = '<span class="badge badge-new">جديد</span>';
                        }
                        
                        html += `
                            <div class="video-card">
                                <div class="video-thumbnail">
                                    ${badges}
                                </div>
                                <div class="video-info">
                                    <div class="video-title">
                                        ${video.caption ? video.caption.substring(0, 100) : 'بدون عنوان'}
                                        ${video.caption && video.caption.length > 100 ? '...' : ''}
                                    </div>
                                    <div class="video-meta">
                                        <div class="video-date">
                                            <i class="far fa-calendar"></i>
                                            ${time_ago || created_at || 'غير معروف'}
                                        </div>
                                        <div class="video-size">
                                            <i class="fas fa-weight-hanging"></i>
                                            ${(video.size_mb || 0).toFixed(1)} MB
                                        </div>
                                    </div>
                                    <div class="video-links">
                                        <a href="${video.public_url}" class="btn btn-view" target="_blank">
                                            <i class="fas fa-eye"></i>
                                            مشاهدة
                                        </a>
                                        <a href="${video.download_url}" class="btn btn-download" target="_blank">
                                            <i class="fas fa-download"></i>
                                            تحميل
                                        </a>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                }
                
                videoGrid.innerHTML = html;
            }
            
            // تحديث عدد الفيديوهات تلقائياً كل 30 ثانية
            function updateStats() {
                fetch('/api/videos')
                    .then(response => response.json())
                    .then(data => {
                        const totalVideos = document.querySelector('.stat-item:first-child p');
                        if (totalVideos) {
                            totalVideos.textContent = data.count;
                        }
                    });
            }
            
            // تحديث كل 30 ثانية
            setInterval(updateStats, 30000);
        </script>
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

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

📎 **معلومات تقنية:**
• الحجم الأصلي: {saved_video['file_size']:,} بايت
• نوع الملف: {saved_video['mime_type']}
• معرف الفيديو: `{saved_video['id']}`

📊 **إجمالي الفيديوهات:** {len(db.get_all_videos())} فيديو
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

async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل المعاد توجيهها التي تحتوي على فيديو"""
    await handle_video_message(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء"""
    logger.error(f"حدث خطأ: {context.error}")
    try:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"⚠️ حدث خطأ في البوت: {context.error}"
        )
    except:
        pass

async def start_bot():
    """تشغيل بوت تلغرام"""
    try:
        # إنشاء التطبيق
        application = Application.builder().token(BOT_TOKEN).build()
        
        # إضافة معالج الأخطاء
        application.add_error_handler(error_handler)
        
        # إضافة handlers
        application.add_handler(MessageHandler(
            filters.VIDEO & filters.Chat(chat_id=int(CHAT_ID)), 
            handle_video_message
        ))
        
        # handler للفيديوهات كملف
        application.add_handler(MessageHandler(
            filters.Document.VIDEO & filters.Chat(chat_id=int(CHAT_ID)), 
            handle_video_message
        ))
        
        # handler للرسائل المعاد توجيهها
        application.add_handler(MessageHandler(
            filters.FORWARDED & (filters.VIDEO | filters.Document.VIDEO) & filters.Chat(chat_id=int(CHAT_ID)), 
            handle_forwarded_message
        ))
        
        # بدء البوت
        await application.initialize()
        await application.start()
        
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot متصل: @{bot_info.username}")
        logger.info(f"📢 يراقب القناة/الجروب: {CHAT_ID}")
        
        # تشغيل البوت
        logger.info("🤖 بدأ البوت في الاستماع للرسائل...")
        await application.updater.start_polling()
        
        # الحفاظ على البوت قيد التشغيل
        while True:
            await asyncio.sleep(1)
        
    except Exception as e:
        logger.error(f"❌ فشل في تشغيل البوت: {e}")
        import traceback
        logger.error(traceback.format_exc())

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
    """تشغيل بوت تلغرام"""
    asyncio.run(start_bot())

def run_keep_alive():
    """تشغيل keep-alive"""
    keep_alive()

if __name__ == "__main__":
    # طباعة معلومات البدء
    print("=" * 70)
    print("🤖 SaveVideoBot - Advanced Video Saver with Public URLs")
    print(f"📢 Channel/Group ID: {CHAT_ID}")
    print(f"📁 Videos Directory: {os.path.abspath(VIDEOS_DIR)}")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"🔗 Public Videos Page: {BASE_URL}/videos")
    print(f"📎 API Endpoints: {BASE_URL}/api/videos")
    print(f"🔍 Search API: {BASE_URL}/api/videos/search?q=كلمة")
    print(f"📊 Total Videos: {len(db.get_all_videos())}")
    print("=" * 70)
    print("\n📋 الميزات المتاحة:")
    print("✅ حفظ تلقائي للفيديوهات من قناة تلغرام")
    print("✅ روابط عامة للمشاهدة والتحميل")
    print("✅ واجهة ويب تفاعلية مع بحث")
    print("✅ API كامل للوصول للبيانات")
    print("✅ معالجة الفيديوهات المعاد توجيهها")
    print("✅ نظام Keep-alive لمنع إيقاف الخادم")
    print("=" * 70)
    
    # إعادة تثبيت المكتبات مع الإصدار الصحيح
    print("\n📦 جاري إعادة تثبيت المكتبات مع الإصدارات الصحيحة...")
    os.system(f"{sys.executable} -m pip install python-telegram-bot==20.7 --force-reinstall")
    
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
        import traceback
        logger.error(traceback.format_exc())
