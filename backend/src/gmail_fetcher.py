import os.path
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import models

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, '..', 'credentials', 'credentials.json')
TOKEN_PATH = os.path.join(BASE_DIR, '..', 'credentials', 'token.json')

# 権限のスコープ
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    """Gmail APIへの接続認証を行う"""
    creds = None
    # すでに認証済みなら token.json を使う
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    # 認証切れ、または未認証の場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # ブラウザを開いてログインを求める
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(f"認証ファイルが見つかりません: {CREDENTIALS_PATH}")
                
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # 次回のために保存
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def fetch_unread_gmails():
    """未読メールを取得して整形する"""
    service = get_gmail_service()
    
    print("Gmailから未読メールを取得中...")
    
    # 未読のメッセージIDリストを取得
    results = service.users().messages().list(
        userId='me', 
        labelIds=['UNREAD'], 
        maxResults=10 # 本番環境は増やす
    ).execute()
    
    messages = results.get('messages', [])
    
    if not messages:
        print("未読メールはありません。")
        return

    email_data_list = []

    # 各メールの詳細情報を取得
    for msg in messages:
        detail = service.users().messages().get(
            userId='me', id=msg['id'], format='full'
        ).execute()
        
        payload = detail.get('payload', {})
        headers = payload.get('headers', [])
        
        subject = "(件名なし)"
        sender = "(不明)"
        for h in headers:
            if h['name'] == 'Subject':
                subject = h['value']
            if h['name'] == 'From':
                sender = h['value']
        
        snippet = detail.get('snippet', '')
        internal_date = int(detail.get('internalDate', 0))
        received_at = datetime.datetime.fromtimestamp(internal_date / 1000.0)

        email_data = {
            'service': 'gmail',
            'message_id': msg['id'],
            'subject': subject,
            'sender': sender,
            'snippet': snippet,
            'received_at': received_at
        }
        email_data_list.append(email_data)
        print(f"取得: {subject[:20]}...")

    # データベースに保存
    models.save_emails(email_data_list)

if __name__ == '__main__':
    # 実行
    fetch_unread_gmails()