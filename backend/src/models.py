import sqlite3
import os
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'db', 'emails.db')

def init_db():
    """データベースとテーブルの初期化"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # emails テーブル: アプリ内で管理するメール
    # message_id: GmailなどのAPIが持つ一意なID (ユニーク制約)
    # status: 0=未読(Inbox), 1=保留(Pending), 2=重要(Important)
    c.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,       -- 'gmail', 'outlook' など
            message_id TEXT NOT NULL UNIQUE,    -- API側のID
            subject TEXT,
            sender TEXT,
            snippet TEXT,
            received_at DATETIME,
            status INTEGER DEFAULT 0    -- 0:Unread, 1:Pending, 2:Important
        )
    ''')
    conn.commit()
    conn.close()

def save_emails(email_list):
    """取得したメールリストをデータベースに保存する"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # リストの中身をタプルの形式に変換
    data = []
    for e in email_list:
        status = e.get('status', 0)
        
        data.append((
            e['service'],
            e['message_id'],
            e['subject'],
            e['sender'],
            e['snippet'],
            e['received_at'],
            status
        ))

    # データベースに保存
    try:
        c.executemany('''
            INSERT OR IGNORE INTO emails 
            (service, message_id, subject, sender, snippet, received_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()
        if c.rowcount > 0:
            print(f"{c.rowcount} 件の新規メールを保存しました")
    except sqlite3.Error as e:
        print(f"保存エラー: {e}")
    finally:
        conn.close()

def get_all_message_ids():
    """DBに保存されている全メールのmessage_idをセット(集合)で返す"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT message_id FROM emails")
    ids = {row[0] for row in c.fetchall()}
    conn.close()
    return ids

def delete_emails(message_ids):
    """指定されたIDのメールをDBから削除する（既読になったため）"""
    if not message_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ','.join('?' for _ in message_ids)
    # タプルに変換して渡す
    c.execute(f"DELETE FROM emails WHERE message_id IN ({placeholders})", list(message_ids))
    conn.commit()
    print(f"{c.rowcount} 件のメールをDBから削除しました（外部で既読化）")
    conn.close()

def get_message_ids_by_service(service_name):
    """指定したサービスのmessage_idのみをセットで返す"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT message_id FROM emails WHERE service=?", (service_name,))
    ids = {row[0] for row in c.fetchall()}
    conn.close()
    return ids

def get_next_email(status=0, offset=0):
    """指定ステータスのメールを1件取得する (古い順, オフセット付き)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 辞書っぽく扱えるようにする
    c = conn.cursor()
    # statusを指定して取得
    c.execute("SELECT * FROM emails WHERE status=? ORDER BY received_at ASC LIMIT 1 OFFSET ?", (status, offset))
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def get_email_by_id(db_id):
    """指定されたDB上のID(主キー)からメール情報を取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM emails WHERE id=?", (db_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def update_email_status(db_id, status):
    """メールのステータスを更新する"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("UPDATE emails SET status = ? WHERE id = ?", (status, db_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"ステータス更新エラー: {e}")
        with open("db_error.log", "a") as f:
            f.write(f"ステータス更新エラー: {e}\n")
        return False
    finally:
        conn.close()

def update_email_status_by_message_id(message_id, status):
    """message_idを指定してステータスを更新する"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 現在のステータスを取得（無駄な更新を防ぐため）
        c.execute("SELECT status FROM emails WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        if row and row[0] != status:
            c.execute("UPDATE emails SET status = ? WHERE message_id = ?", (status, message_id))
            conn.commit()
            print(f"ステータス更新({message_id}): {row[0]} -> {status}")
            return True
    except Exception as e:
        print(f"ステータス更新エラー: {e}")
    finally:
        conn.close()
    return False

# 初期化実行
if __name__ == "__main__":
    init_db()
    print("データベース作成")