from flask import Flask, jsonify, request, send_from_directory
import os
import models
import gmail_fetcher
import imap_fetcher
import outlook_fetcher

app = Flask(__name__, static_folder='../../frontend')

# 静的ファイルの提供 (index.htmlなど)
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/read')
def read_page():
    return send_from_directory(app.static_folder, 'read.html')

@app.route('/important')
def important_page():
    return send_from_directory(app.static_folder, 'important.html')

@app.route('/hold')
def hold_page():
    return send_from_directory(app.static_folder, 'hold.html')

@app.route('/api/emails/<int:db_id>/read', methods=['POST'])
def mark_as_read(db_id):
    """メールを既読にする"""
    email = models.get_email_by_id(db_id)
    if not email:
        return jsonify({'error': 'Email not found'}), 404
        
    service = email['service']
    message_id = email['message_id']
    success = False
    
    if service == 'gmail':
        success = gmail_fetcher.mark_as_read(message_id)
    elif service.startswith('imap:'):
        success = imap_fetcher.mark_as_read(service, message_id)
    elif service == 'outlook':
        success = outlook_fetcher.mark_as_read(message_id)
    else:
        # いったんDB削除だけしておく
        success = True
        print(f"Warning: {service} の既読連携は未実装です。DBからのみ削除します。")


    if success:
        # DBから削除（またはステータス更新）
        # 今回の要件では「既読になったらリストから消える」＝DB削除 or status=1
        # models.delete_emails を使うとDBから消える
        models.delete_emails([message_id])
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to mark as read'}), 500

@app.route('/api/emails/<int:db_id>/pending', methods=['POST'])
def mark_as_pending(db_id):
    """メールを保留にする"""
    if models.update_email_status(db_id, 1): # 1: Pending
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to update status'}), 500

@app.route('/api/emails/<int:db_id>/important', methods=['POST'])
def mark_as_important(db_id):
    """メールを重要にする（外部連携あり）"""
    email = models.get_email_by_id(db_id)
    if not email:
        return jsonify({'error': 'Email not found'}), 404
        
    service = email['service']
    message_id = email['message_id']
    success = False
    
    # 各サービスの重要(スター/フラグ)処理を呼び出し
    if service == 'gmail':
        success = gmail_fetcher.mark_as_important(message_id)
    elif service.startswith('imap:'):
        success = imap_fetcher.mark_as_important(service, message_id)
    elif service == 'outlook':
        success = outlook_fetcher.mark_as_important(message_id)
    else:
        success = True
        print(f"Warning: {service} の重要連携は未実装です。")

    if success:
        # 連携に成功したらDBのステータスを更新 (2: Important)
        if models.update_email_status(db_id, 2): 
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update local status'}), 500
    else:
        return jsonify({'error': 'Failed to mark as important on server'}), 500

@app.route('/api/emails/<int:db_id>/unimportant', methods=['POST'])
def mark_as_unimportant(db_id):
    """メールを重要から削除する（スター/フラグを外す）"""
    email = models.get_email_by_id(db_id)
    if not email:
        return jsonify({'error': 'Email not found'}), 404
        
    service = email['service']
    message_id = email['message_id']
    success = False
    
    # 各サービスの重要解除処理を呼び出し
    if service == 'gmail':
        success = gmail_fetcher.mark_as_unimportant(message_id)
    elif service.startswith('imap:'):
        success = imap_fetcher.mark_as_unimportant(service, message_id)
    elif service == 'outlook':
        success = outlook_fetcher.mark_as_unimportant(message_id)
    else:
        success = True
        print(f"Warning: {service} の重要解除連携は未実装です。")

    if success:
        # 成功したらステータスを未読(0)に戻す
        if models.update_email_status(db_id, 0): # 0: Unread
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update local status'}), 500
    else:
        return jsonify({'error': 'Failed to mark as unimportant on server'}), 500
    
@app.route('/api/emails/next', methods=['GET'])
def get_next_email():
    """メールを1件取得 (status指定可)"""
    # クエリパラメータからoffsetを取得 (デフォルトは0)
    offset = request.args.get('offset', default=0, type=int)
    # status: 0=Unread, 1=Pending, 2=Important
    status = request.args.get('status', default=0, type=int)
    
    email = models.get_next_email(status=status, offset=offset)
    if email:
        return jsonify(email)
    else:
        return jsonify(None), 404

@app.route('/api/emails/<int:db_id>/delete', methods=['POST'])
def delete_email_route(db_id):
    """メールをサーバーから削除し、DBからも消す"""
    email = models.get_email_by_id(db_id)
    if not email:
        return jsonify({'error': 'Email not found'}), 404
        
    service = email['service']
    message_id = email['message_id']
    success = False
    
    # サービスごとの削除処理を実行
    if service == 'gmail':
        success = gmail_fetcher.delete_email(message_id)
    elif service.startswith('imap:'):
        success = imap_fetcher.delete_email(service, message_id)
    elif service == 'outlook':
        success = outlook_fetcher.delete_email(message_id)
    else:
        # 未知のサービスならDB削除のみ許可
        success = True
        print(f"Warning: {service} の削除連携は未実装です。DBからのみ削除します。")

    if success:
        # DBから削除
        models.delete_emails([message_id])
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to delete email'}), 500

@app.route('/api/fetch/gmail', methods=['POST'])
def fetch_gmail():
    """Gmailの同期を手動実行"""
    try:
        gmail_fetcher.sync_gmail()
        return jsonify({'success': True, 'message': 'Gmail sync started'})
    except Exception as e:
        print(f"Gmail sync error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fetch/outlook', methods=['POST'])
def fetch_outlook():
    """Outlookの同期を手動実行"""
    try:
        outlook_fetcher.sync_outlook()
        return jsonify({'success': True, 'message': 'Outlook sync started'})
    except Exception as e:
        print(f"Outlook sync error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fetch/imap', methods=['POST'])
def fetch_imap():
    """IMAPの同期を手動実行"""
    try:
        imap_fetcher.sync_imap_all()
        return jsonify({'success': True, 'message': 'IMAP sync started'})
    except Exception as e:
        print(f"IMAP sync error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # DB初期化確認
    models.init_db()
    app.run(debug=True, port=5002)