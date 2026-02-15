import sqlite3
from datetime import datetime

DB_NAME = "emails.db"

def init_db():
    """データベースとテーブルの初期化"""
    conn = sqlite3.connect(DB_NAME)
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

# 初期化実行
if __name__ == "__main__":
    init_db()
    print("データベース作成")