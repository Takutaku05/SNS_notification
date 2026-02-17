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

    service_name = f"imap:{account_config['username']}"
    email_data_list = []
    count = 0

    prefix_len = len(account_prefix) + 1 
    
    target_pairs = [] 
    for tid in target_ids_with_prefix:
        uid = tid[prefix_len:]
        target_pairs.append((tid, uid))

    for db_id, uid in target_pairs:
        if count >= 10: 
            print(f"[{account_config['username']}] 上限(10件)のため中断")
            break

        try:
            # フラグ情報も同時に取得するため (RFC822 FLAGS) とする
            status, data = mail.fetch(uid, '(RFC822 FLAGS)')
            if status != 'OK' or not data or data[0] is None:
                continue

            # data構造の解析: [ (b'SEQ (FLAGS (...) RFC822 {LEN}', b'BODY...'), b')' ]
            # フラグは通常 data[0][0] のバイト列の中に含まれる
            response_header = data[0][0] 
            raw_email = data[0][1]
            
            # フラグ判定: \Flagged が含まれているか
            # response_header は bytes なので b'\\Flagged' を探す
            is_flagged = b'\\Flagged' in response_header
            db_status = 2 if is_flagged else 0

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
                'service': service_name,
                'message_id': db_id,
                'subject': subject,
                'sender': from_header,
                'snippet': snippet,
                'received_at': received_at,
                'status': db_status
            })
            
            status_str = "★重要" if db_status == 2 else "未読"
            print(f"[{account_config['username']}] 取得: {subject[:15]}... [{status_str}]")
            count += 1

        except Exception as e:
            print(f"エラー(UID: {uid}): {e}")

    if email_data_list:
        models.save_emails(email_data_list)

def update_flagged_status(mail, existing_ids_with_prefix, account_prefix):
    """既存メールのフラグ状態をIMAPサーバーと同期する"""
    if not existing_ids_with_prefix:
        return

    prefix_len = len(account_prefix) + 1
    
    # UIDリストを作成
    uids = []
    uid_map = {} # uid -> db_id
    for tid in existing_ids_with_prefix:
        uid = tid[prefix_len:]
        uids.append(uid)
        uid_map[uid] = tid

    # まとめてフラグ取得 (UID FETCH 1,2,3 (FLAGS))
    if not uids:
        return

    uid_str = ",".join(uids)
    try:
        status, data = mail.uid('fetch', uid_str, '(FLAGS)')
        if status == 'OK':
            for item in data:
                if not item or item == b')': continue
                
                # item例: b'123 (UID 123 FLAGS (\Seen \Flagged))'
                # parseが面倒なので簡易的にチェック
                
                # UIDを抽出
                item_str = item.decode('utf-8', errors='ignore') if isinstance(item, bytes) else str(item)
                
                # UID特定 (簡易実装: 文字列内から探す)
                # 正確には正規表現などで "UID <number>" を抜くべきだが、
                # ここではループ中のUIDを使ってマッチングする
                target_uid = None
                for u in uids:
                    if f"UID {u}" in item_str:
                        target_uid = u
                        break
                
                if target_uid:
                    is_flagged = '\\Flagged' in item_str
                    new_status = 2 if is_flagged else 0
                    
                    db_id = uid_map[target_uid]
                    models.update_email_status_by_message_id(db_id, new_status)
                    
    except Exception as e:
        print(f"フラグ同期エラー: {e}")

def sync_one_account(account_config):
    """1つのアカウントについて同期処理を行う"""
    username = account_config['username']
    print(f"--- {username} の同期開始 ---")

    mail = get_imap_connection(account_config)
    if not mail:
        return

    account_prefix = f"imap_{username}"
    service_key = f"imap:{username}"

    try:
        # 1. サーバー(IMAP)にある未読ID
        server_unread_ids = fetch_all_unread_ids(mail, account_prefix)

        # 2. ローカル(DB)にある このアカウントの IDのみを取得
        local_stored_ids = models.get_message_ids_by_service(service_key)

        # 3. 差分計算
        new_ids = server_unread_ids - local_stored_ids
        read_ids = local_stored_ids - server_unread_ids
        existing_ids = server_unread_ids & local_stored_ids

        # 4. DB更新
        if read_ids:
            print(f"既読検知: {len(read_ids)} 件 -> 削除")
            models.delete_emails(read_ids)
        
        if new_ids:
            print(f"新着検知: {len(new_ids)} 件 -> 取得")
            fetch_details_and_save(mail, new_ids, account_config, account_prefix)

        # 5. 既存メールのフラグ同期
        if existing_ids:
            update_flagged_status(mail, existing_ids, account_prefix)
            
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

def mark_as_read(service_name, message_id):
    """IMAPのメールを既読にする"""
    if not service_name.startswith('imap:'):
        return False
        
    target_username = service_name.replace('imap:', '')
    
    if not os.path.exists(CREDENTIALS_PATH):
        return False

    with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
        
    target_account = None
    for account in accounts:
        if account['username'] == target_username:
            target_account = account
            break
            
    if not target_account:
        print(f"アカウント設定が見つかりません: {target_username}")
        return False
        
    mail = get_imap_connection(target_account)
    if not mail:
        return False
        
    try:
        mail.select('INBOX')
        
        prefix = f"imap_{target_username}_"
        if not message_id.startswith(prefix):
             print(f"ID形式エラー: {message_id}")
             return False
             
        uid = message_id[len(prefix):]
        
        mail.store(uid, '+FLAGS', '\\Seen')
        print(f"IMAP既読化成功: {uid} ({target_username})")
        return True
        
    except Exception as e:
        print(f"IMAP既読化エラー: {e}")
        return False
    finally:
        try:
            mail.logout()
        except:
            pass

def mark_as_important(service_name, message_id):
    """IMAPのメールにフラグ(\Flagged)を立てる"""
    if not service_name.startswith('imap:'):
        return False
        
    target_username = service_name.replace('imap:', '')
    
    if not os.path.exists(CREDENTIALS_PATH):
        return False

    with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
        
    target_account = None
    for account in accounts:
        if account['username'] == target_username:
            target_account = account
            break
            
    if not target_account:
        print(f"アカウント設定が見つかりません: {target_username}")
        return False
        
    mail = get_imap_connection(target_account)
    if not mail:
        return False
        
    try:
        mail.select('INBOX')
        
        prefix = f"imap_{target_username}_"
        if not message_id.startswith(prefix):
             print(f"ID形式エラー: {message_id}")
             return False
             
        uid = message_id[len(prefix):]
        
        mail.store(uid, '+FLAGS', '\\Flagged')
        print(f"IMAP重要設定(フラグ)成功: {uid} ({target_username})")
        return True
        
    except Exception as e:
        print(f"IMAP重要設定エラー: {e}")
        return False
    finally:
        try:
            mail.logout()
        except:
            pass

def mark_as_unimportant(service_name, message_id):
    """IMAPのメールからフラグ(\Flagged)を外す"""
    if not service_name.startswith('imap:'):
        return False
        
    target_username = service_name.replace('imap:', '')
    
    if not os.path.exists(CREDENTIALS_PATH):
        return False

    with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
        
    target_account = None
    for account in accounts:
        if account['username'] == target_username:
            target_account = account
            break
            
    if not target_account:
        print(f"アカウント設定が見つかりません: {target_username}")
        return False
        
    mail = get_imap_connection(target_account)
    if not mail:
        return False
        
    try:
        mail.select('INBOX')
        
        prefix = f"imap_{target_username}_"
        if not message_id.startswith(prefix):
             print(f"ID形式エラー: {message_id}")
             return False
             
        uid = message_id[len(prefix):]
        
        # フラグを外す (-FLAGS)
        mail.store(uid, '-FLAGS', '\\Flagged')
        print(f"IMAP重要解除(フラグ削除)成功: {uid} ({target_username})")
        return True
        
    except Exception as e:
        print(f"IMAP重要解除エラー: {e}")
        return False
    finally:
        try:
            mail.logout()
        except:
            pass

if __name__ == '__main__':
    models.init_db()
    sync_imap_all()

def delete_email(service_name, message_id):
    """IMAPのメールに削除フラグを立てて削除する"""
    if not service_name.startswith('imap:'):
        return False
        
    target_username = service_name.replace('imap:', '')
    
    if not os.path.exists(CREDENTIALS_PATH):
        return False

    with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
        
    target_account = None
    for account in accounts:
        if account['username'] == target_username:
            target_account = account
            break
            
    if not target_account:
        print(f"アカウント設定が見つかりません: {target_username}")
        return False
        
    mail = get_imap_connection(target_account)
    if not mail:
        return False
        
    try:
        mail.select('INBOX')
        
        # message_id は "imap_user@example.com_123" の形式
        prefix = f"imap_{target_username}_"
        if not message_id.startswith(prefix):
             print(f"ID形式エラー: {message_id}")
             return False
             
        uid = message_id[len(prefix):]
        
        # 削除フラグを立てる
        mail.store(uid, '+FLAGS', '\\Deleted')
        # サーバーによってはEXPUNGEが必要（完全に削除）
        mail.expunge()
        
        print(f"IMAP削除成功: {uid} ({target_username})")
        return True
        
    except Exception as e:
        print(f"IMAP削除エラー: {e}")
        return False
    finally:
        try:
            mail.logout()
        except:
            pass
