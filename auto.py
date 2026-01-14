import os
import time
import json
import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import schedule
import base64
import pickle

# Constants
SCOPES = ['https://www.googleapis.com/auth/drive.file']
GOOGLE_DRIVE_FOLDER_ID = '10Hk6ZQaDiXuHe-k8J9_Rc11UeQ7iTE14'
INSTAGRAM_ACCOUNT_ID = '61219445676'
INSTAGRAM_GRAPH_API_TOKEN = 'EAAaoHv9aJ5gBQTq7k7V019hwK5eybC3ZCrrErXsAZBUZC3pTGk2JDxJPSlUoJfVR0nDLtFfdmixZAZAodls8a80kXuBDuxJ1RZCfEKp8QB6qrKFgskF4ewuuVG4LzRD6lfrYrLlpt4liOEqe91bRWxwA7z482zewY8TbOyH3CnwtSuUWtXYnxsLNWk344nQ8zEix7WI1Tja3tWxTzboZAMTZCSusiSOwdJni3HctIVkZD'

# Google Drive Client Credentials
GOOGLE_CLIENT_ID = '468168778821-mr3jp6kj5ssomi8vc25q9h8pc05egtqe.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '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'
GOOGLE_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'

# Load or refresh Google Drive credentials
def get_google_drive_credentials():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": GOOGLE_CLIENT_ID,
                        "project_id": "your-project-id",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "redirect_uris": [GOOGLE_REDIRECT_URI]
                    }
                },
                SCOPES
            )
            creds = flow.run_console()
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

# Upload video to Google Drive
def upload_video_to_drive(video_path, caption):
    creds = get_google_drive_credentials()
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': os.path.basename(video_path),
        'parents': [GOOGLE_DRIVE_FOLDER_ID],
        'description': caption
    }
    media = MediaFileUpload(video_path, mimetype='video/mp4')
    file = service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
    return file.get('id'), file.get('webViewLink')

# Delete video from Google Drive
def delete_video_from_drive(file_id):
    creds = get_google_drive_credentials()
    service = build('drive', 'v3', credentials=creds)
    service.files().delete(fileId=file_id).execute()

# Publish video to Instagram
def publish_video_to_instagram(video_url, caption):
    url = f'https://graph.facebook.com/v17.0/{INSTAGRAM_ACCOUNT_ID}/media'
    payload = {
        'video_url': video_url,
        'caption': caption,
        'access_token': INSTAGRAM_GRAPH_API_TOKEN
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        creation_id = response.json().get('id')
        publish_url = f'https://graph.facebook.com/v17.0/{INSTAGRAM_ACCOUNT_ID}/media_publish'
        publish_payload = {
            'creation_id': creation_id,
            'access_token': INSTAGRAM_GRAPH_API_TOKEN
        }
        publish_response = requests.post(publish_url, data=publish_payload)
        if publish_response.status_code == 200:
            return True, publish_response.json().get('id')
        else:
            print(f"Error publishing video: {publish_response.text}")
            return False, None
    else:
        print(f"Error uploading video: {response.text}")
        return False, None

# Process video
def process_video(video_path, caption):
    file_id, video_url = upload_video_to_drive(video_path, caption)
    print(f"Uploaded video to Google Drive: {video_url}")
    success, post_id = publish_video_to_instagram(video_url, caption)
    if success:
        print(f"Published video to Instagram: {post_id}")
        delete_video_from_drive(file_id)
        print(f"Deleted video from Google Drive: {file_id}")
    else:
        print("Failed to publish video to Instagram")

# Main loop
def main_loop():
    videos_dir = 'videos'
    video_files = sorted([f for f in os.listdir(videos_dir) if f.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'))])
    
    for video_file in video_files:
        video_path = os.path.join(videos_dir, video_file)
        caption = os.path.splitext(video_file)[0]  # Use filename as caption
        process_video(video_path, caption)
        time.sleep(300)  # Wait for 5 minutes

    # Repeat the loop
    schedule.every(5).minutes.do(main_loop)

# Start the loop
if __name__ == '__main__':
    main_loop()
    while True:
        schedule.run_pending()
        time.sleep(1)
