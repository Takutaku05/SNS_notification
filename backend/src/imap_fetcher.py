import imaplib
import email
import email.header
import json
import os
import datetime
import models

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, '..', 'credentials', 'imap_credentials.json')

def get_imap_connection(account_config):
    """指定された設定でIMAPサーバーに接続してログインする"""
    host = account_config.get('host')
    port = account_config.get('port', 993)
    username = account_config.get('username')
    password = account_config.get('password')

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(username, password)
        return mail
    except Exception as e:
        print(f"[{username}] 接続エラー: {e}")
        return None

def decode_header_value(header_value):
    """メールヘッダーのデコード処理"""
    if not header_value:
        return ""
    
    decoded_fragments = email.header.decode_header(header_value)
    result = ""
    for bytes_fragment, encoding in decoded_fragments:
        if isinstance(bytes_fragment, bytes):
            if encoding:
                try:
                    result += bytes_fragment.decode(encoding)
                except LookupError:
                    result += bytes_fragment.decode('utf-8', errors='replace')
            else:
                result += bytes_fragment.decode('utf-8', errors='replace')
        else:
            result += str(bytes_fragment)
    return result

def get_body_snippet(msg):
    """メール本文から簡易的なスニペットを抽出"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
    
    return " ".join(body.split())[:100]

def fetch_all_unread_ids(mail, account_prefix):
    """指定アカウントの未読IDを取得 (prefixを付与してユニークにする)"""
    mail.select('INBOX')
    status, data = mail.search(None, 'UNSEEN')
    if status != 'OK':
        return set()

    raw_ids = data[0].split()
    # 他のアカウントとIDが被らないよう、プレフィックスにメールアドレスなどを含める
    return {f"{account_prefix}_{uid.decode()}" for uid in raw_ids}

def fetch_details_and_save(mail, target_ids_with_prefix, account_config, account_prefix):
    """詳細を取得して保存"""
    if not target_ids_with_prefix:
        return

    # DB上のservice名は 'imap:メールアドレス' とする
    service_name = f"imap:{account_config['username']}"
    email_data_list = []
    count = 0

    # プレフィックスを除去してIMAPのUIDに戻す
    # 例: "imap_user1@yahoo_123" -> "123"
    prefix_len = len(account_prefix) + 1 # '_' の分+1
    
    # 処理しやすいように ID と UID のペアを作る
    target_pairs = [] 
    for tid in target_ids_with_prefix:
        uid = tid[prefix_len:]
        target_pairs.append((tid, uid))

    for db_id, uid in target_pairs:
        if count >= 30: # アカウントごとの取得上限
            print(f"[{account_config['username']}] 上限(30件)のため中断")
            break

        try:
            status, data = mail.fetch(uid, '(RFC822)')
            if status != 'OK' or not data or data[0] is None:
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = decode_header_value(msg.get('Subject', '(件名なし)'))
            from_header = decode_header_value(msg.get('From', '(不明)'))
            
            date_header = msg.get('Date')
            if date_header:
                try:
                    received_at = email.utils.parsedate_to_datetime(date_header)
                except:
                    received_at = datetime.datetime.now()
            else:
                received_at = datetime.datetime.now()

            snippet = get_body_snippet(msg)

            email_data_list.append({
                'service': service_name,   # どのアカウントのデータか区別可能にする
                'message_id': db_id,       # ユニークなID (imap_user@..._123)
                'subject': subject,
                'sender': from_header,
                'snippet': snippet,
                'received_at': received_at
            })
            print(f"[{account_config['username']}] 取得: {subject[:15]}...")
            count += 1

        except Exception as e:
            print(f"エラー(UID: {uid}): {e}")

    if email_data_list:
        models.save_emails(email_data_list)

def sync_one_account(account_config):
    """1つのアカウントについて同期処理を行う"""
    username = account_config['username']
    print(f"--- {username} の同期開始 ---")

    mail = get_imap_connection(account_config)
    if not mail:
        return

    # IDの衝突を防ぐため、プレフィックスにユーザー名を含める
    # DBの message_id = "imap_user1@example.com_123" のようになります
    account_prefix = f"imap_{username}"
    
    # DBの service カラムもアカウントごとに分ける
    service_key = f"imap:{username}"

    try:
        # 1. サーバー(IMAP)にある未読ID
        server_unread_ids = fetch_all_unread_ids(mail, account_prefix)

        # 2. ローカル(DB)にある このアカウントの IDのみを取得
        # models.py の get_message_ids_by_service を利用
        local_stored_ids = models.get_message_ids_by_service(service_key)

        # 3. 差分計算
        new_ids = server_unread_ids - local_stored_ids
        read_ids = local_stored_ids - server_unread_ids

        # 4. DB更新
        if read_ids:
            print(f"既読検知: {len(read_ids)} 件 -> 削除")
            models.delete_emails(read_ids)
        
        if new_ids:
            print(f"新着検知: {len(new_ids)} 件 -> 取得")
            fetch_details_and_save(mail, new_ids, account_config, account_prefix)
            
    except Exception as e:
        print(f"同期エラー: {e}")
    finally:
        try:
            mail.logout()
        except:
            pass

def sync_imap_all():
    """全IMAPアカウントを同期するメイン関数"""
    if not os.path.exists(CREDENTIALS_PATH):
        print("設定ファイルが見つかりません")
        return

    with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
        accounts = json.load(f)

    if not isinstance(accounts, list):
        print("エラー: imap_credentials.json はリスト形式である必要があります。")
        return

    for account in accounts:
        sync_one_account(account)

if __name__ == '__main__':
    models.init_db()
    sync_imap_all()