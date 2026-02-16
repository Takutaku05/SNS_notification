import os
import json
import atexit
import datetime
import requests
import msal
import models

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, '..', 'credentials', 'outlook_credentials.json')
TOKEN_PATH = os.path.join(BASE_DIR, '..', 'credentials', 'outlook_token.json')

# 設定
SCOPES = ['User.Read', 'Mail.ReadWrite']
GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'

def get_access_token():
    """Microsoft Graph APIのアクセストークンを取得する"""
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(f"認証ファイルが見つかりません: {CREDENTIALS_PATH}")

    with open(CREDENTIALS_PATH, 'r') as f:
        creds = json.load(f)
        client_id = creds.get('client_id')

    # トークンキャッシュの読み込み
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'r') as f:
            cache.deserialize(f.read())

    # 終了時にキャッシュを保存
    def save_cache():
        if cache.has_state_changed:
            with open(TOKEN_PATH, 'w') as f:
                f.write(cache.serialize())
    atexit.register(save_cache)

    app = msal.PublicClientApplication(
        client_id,
        authority="https://login.microsoftonline.com/consumers",
        token_cache=cache
    )

    result = None
    accounts = app.get_accounts()
    
    if accounts:
        # キャッシュからトークン取得を試みる
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        # 初回はブラウザでログイン
        print("Outlook: ブラウザでログインしてください...")
        result = app.acquire_token_interactive(scopes=SCOPES)

    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(f"トークン取得失敗: {result.get('error_description')}")

def fetch_all_unread_ids():
    """Outlook上の全未読メールのIDだけを取得する"""
    token = get_access_token()
    headers = {'Authorization': 'Bearer ' + token}
    
    unread_ids = set()
    url = f"{GRAPH_API_ENDPOINT}/me/messages"
    
    # 未読のみ、IDのみ取得
    params = {
        '$filter': 'isRead eq false',
        '$select': 'id',
        '$top': 100
    }

    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"API Error: {response.text}")
            break
            
        data = response.json()
        messages = data.get('value', [])
        
        for msg in messages:
            unread_ids.add(msg['id'])
        
        # 次のページがある場合
        url = data.get('@odata.nextLink')
        params = None # nextLinkにはパラメータが含まれているため

    return unread_ids

def fetch_details_and_save(target_ids):
    """指定されたIDリストのメール詳細を取得して保存"""
    if not target_ids:
        return

    token = get_access_token()
    headers = {'Authorization': 'Bearer ' + token}
    email_data_list = []
    
    count = 0
    for msg_id in target_ids:
        if count >= 10:
            print("一度の取得上限(10件)に達したため中断します")
            break

        try:
            # 詳細取得
            url = f"{GRAPH_API_ENDPOINT}/me/messages/{msg_id}"
            params = {'$select': 'subject,from,bodyPreview,receivedDateTime'}
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 404:
                print(f"メッセージが見つかりません (ID: {msg_id})")
                continue
                
            detail = response.json()
            
            subject = detail.get('subject', '(件名なし)')
            sender_info = detail.get('from', {}).get('emailAddress', {})
            sender = f"{sender_info.get('name', '')} <{sender_info.get('address', '')}>"
            snippet = detail.get('bodyPreview', '')
            
            # 日時パース
            received_str = detail.get('receivedDateTime')
            if received_str:
                received_at = datetime.datetime.fromisoformat(received_str.replace('Z', '+00:00'))
            else:
                received_at = datetime.datetime.now()

            email_data_list.append({
                'service': 'outlook',
                'message_id': msg_id,
                'subject': subject,
                'sender': sender,
                'snippet': snippet,
                'received_at': received_at
            })
            print(f"取得(Outlook): {subject[:20]}...")
            count += 1
            
        except Exception as e:
            print(f"エラー(ID: {msg_id}): {e}")

    if email_data_list:
        models.save_emails(email_data_list)

def sync_outlook():
    """OutlookとDBを同期する"""
    print("Outlookの同期を開始します...")
    
    # 1. サーバーにある未読ID
    try:
        server_unread_ids = fetch_all_unread_ids()
    except Exception as e:
        print(f"Outlookへの接続に失敗しました: {e}")
        return

    # 2. DBにあるOutlookのID (★重要: GmailのIDと混ぜないため指定して取得)
    # models.py に新しく追加する関数を使います
    if hasattr(models, 'get_message_ids_by_service'):
        local_stored_ids = models.get_message_ids_by_service('outlook')
    else:
        # 関数がない場合のフォールバック（推奨されません）
        print("警告: models.pyが更新されていないため、同期が不正確になる可能性があります。")
        local_stored_ids = models.get_all_message_ids()

    # 3. 差分計算
    new_ids = server_unread_ids - local_stored_ids
    read_ids = local_stored_ids - server_unread_ids
    
    # 4. DB更新
    if read_ids:
        print(f"既読検知(Outlook): {len(read_ids)} 件 -> DBから削除します")
        models.delete_emails(read_ids)
    
    if new_ids:
        print(f"新着検知(Outlook): {len(new_ids)} 件 -> 詳細を取得して保存します")
        fetch_details_and_save(new_ids)

def mark_as_read(message_id):
    """Outlookのメールを既読にする"""
    token = get_access_token()
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    
    url = f"{GRAPH_API_ENDPOINT}/me/messages/{message_id}"
    data = {'isRead': True}

    try:
        # PATCHメソッドで更新
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"Outlook既読化成功: {message_id}")
            return True
        else:
            print(f"Outlook既読化失敗: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Outlook既読化エラー: {e}")
        return False

if __name__ == '__main__':
    models.init_db()
    sync_outlook()