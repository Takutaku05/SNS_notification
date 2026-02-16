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
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(f"認証ファイルが見つかりません: {CREDENTIALS_PATH}")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def fetch_all_unread_ids():
    """Gmail上の全未読メールのIDだけを取得する"""
    service = get_gmail_service()
    
    unread_ids = set()
    page_token = None
    
    while True:
        # IDだけ欲しいので fields='messages(id),nextPageToken' で通信量を節約
        results = service.users().messages().list(
            userId='me', 
            labelIds=['UNREAD'], 
            fields='messages(id),nextPageToken',
            pageToken=page_token
        ).execute()
        
        messages = results.get('messages', [])
        for msg in messages:
            unread_ids.add(msg['id'])
            
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    return unread_ids

def fetch_details_and_save(target_ids):
    """指定されたIDリストのメール詳細を取得して保存"""
    service = get_gmail_service()
    email_data_list = []
    
    # 一度に大量に処理しすぎないようループ（ここではシンプルに実装）
    count = 0
    for msg_id in target_ids:
        # 最大50件などで制限したい場合はここでbreakしてもOK
        if count >= 50: 
            print("一度の取得上限(50件)に達したため中断します")
            break

        try:
            detail = service.users().messages().get(
                userId='me', id=msg_id, format='full'
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

            email_data_list.append({
                'service': 'gmail',
                'message_id': msg_id,
                'subject': subject,
                'sender': sender,
                'snippet': snippet,
                'received_at': received_at
            })
            print(f"取得: {subject[:20]}...")
            count += 1
            
        except Exception as e:
            print(f"エラー(ID: {msg_id}): {e}")

    if email_data_list:
        models.save_emails(email_data_list)

def sync_gmails():
    """GmailとDBを同期する（新規取得 ＋ 既読削除）"""
    print("同期を開始します...")
    
    # 1. サーバー(Gmail)にある未読IDを取得
    server_unread_ids = fetch_all_unread_ids()
    
    # 2. ローカル(DB)にあるIDを取得
    local_stored_ids = models.get_all_message_ids()
    
    # 3. 差分を計算（集合演算）
    
    # 新しく来たメール (サーバーにはあるが、DBにはない)
    new_ids = server_unread_ids - local_stored_ids
    
    # 他で既読になったメール (DBにはあるが、サーバーにはない)
    read_ids = local_stored_ids - server_unread_ids
    
    # 4. DBを更新
    
    # 既読になったものを削除
    if read_ids:
        print(f"既読検知: {len(read_ids)} 件 -> DBから削除します")
        models.delete_emails(read_ids)
    
    # 新着メールを取得して保存
    if new_ids:
        print(f"新着検知: {len(new_ids)} 件 -> 詳細を取得して保存します")
        fetch_details_and_save(new_ids)
    
    if not read_ids and not new_ids:
        print("変更はありません（最新の状態です）")

if __name__ == '__main__':
    models.init_db()
    sync_gmails()