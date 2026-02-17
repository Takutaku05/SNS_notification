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
            # 詳細取得 (flag も取得項目に追加)
            url = f"{GRAPH_API_ENDPOINT}/me/messages/{msg_id}"
            params = {'$select': 'subject,from,bodyPreview,receivedDateTime,flag'}
            
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

            # フラグ判定
            # flag: { "flagStatus": "flagged" } または "notFlagged"
            flag_status = detail.get('flag', {}).get('flagStatus')
            status = 2 if flag_status == 'flagged' else 0

            email_data_list.append({
                'service': 'outlook',
                'message_id': msg_id,
                'subject': subject,
                'sender': sender,
                'snippet': snippet,
                'received_at': received_at,
                'status': status
            })
            
            status_str = "★重要" if status == 2 else "未読"
            print(f"取得(Outlook): {subject[:20]}... [{status_str}]")
            count += 1
            
        except Exception as e:
            print(f"エラー(ID: {msg_id}): {e}")

    if email_data_list:
        models.save_emails(email_data_list)

def update_flagged_status(local_ids):
    """DBにあるメールのフラグ状態をOutlookと同期する"""
    if not local_ids:
        return

    token = get_access_token()
    headers = {'Authorization': 'Bearer ' + token}
    
    print(f"既存メール({len(local_ids)}件)のステータスを確認中(Outlook)...")

    # Outlookはバッチ取得も可能ですが、実装を簡単にするためループ処理します
    for msg_id in local_ids:
        try:
            url = f"{GRAPH_API_ENDPOINT}/me/messages/{msg_id}"
            params = {'$select': 'flag'} # フラグ情報だけ取得
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                flag_status = data.get('flag', {}).get('flagStatus')
                new_status = 2 if flag_status == 'flagged' else 0
                
                models.update_email_status_by_message_id(msg_id, new_status)
            elif response.status_code == 404:
                pass # 削除済み
        except Exception as e:
            print(f"ステータス確認エラー(Outlook): {e}")

def sync_outlook():
    """OutlookとDBを同期する"""
    print("Outlookの同期を開始します...")
    
    # 1. サーバーにある未読ID
    try:
        server_unread_ids = fetch_all_unread_ids()
    except Exception as e:
        print(f"Outlookへの接続に失敗しました: {e}")
        return

    # 2. DBにあるOutlookのID
    if hasattr(models, 'get_message_ids_by_service'):
        local_stored_ids = models.get_message_ids_by_service('outlook')
    else:
        local_stored_ids = models.get_all_message_ids()

    # 3. 差分計算
    new_ids = server_unread_ids - local_stored_ids
    read_ids = local_stored_ids - server_unread_ids
    existing_ids = server_unread_ids & local_stored_ids
    
    # 4. DB更新
    if read_ids:
        print(f"既読検知(Outlook): {len(read_ids)} 件 -> DBから削除します")
        models.delete_emails(read_ids)
    
    if new_ids:
        print(f"新着検知(Outlook): {len(new_ids)} 件 -> 詳細を取得して保存します")
        fetch_details_and_save(new_ids)
        
    # 5. 既存メールのフラグ状態を同期
    if existing_ids:
        update_flagged_status(existing_ids)

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
    
def mark_as_important(message_id):
    """Outlookのメールにフラグを立てる"""
    token = get_access_token()
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    
    url = f"{GRAPH_API_ENDPOINT}/me/messages/{message_id}"
    data = {'flag': {'flagStatus': 'flagged'}}

    try:
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"Outlook重要設定(フラグ)成功: {message_id}")
            return True
        else:
            print(f"Outlook重要設定失敗: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Outlook重要設定エラー: {e}")
        return False

def mark_as_unimportant(message_id):
    """Outlookのメールからフラグを外す"""
    token = get_access_token()
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    
    url = f"{GRAPH_API_ENDPOINT}/me/messages/{message_id}"
    # フラグを外すには flagStatus: 'notFlagged'
    data = {'flag': {'flagStatus': 'notFlagged'}}

    try:
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"Outlook重要解除(フラグ削除)成功: {message_id}")
            return True
        else:
            print(f"Outlook重要解除失敗: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Outlook重要解除エラー: {e}")
        return False

if __name__ == '__main__':
    models.init_db()
    sync_outlook()