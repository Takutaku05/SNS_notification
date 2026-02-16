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
    """メールを重要にする"""
    if models.update_email_status(db_id, 2): # 2: Important
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to update status'}), 500
    
@app.route('/api/emails/next', methods=['GET'])
def get_next_unread_email():
    """未読メールを1件取得"""
    # クエリパラメータからoffsetを取得 (デフォルトは0)
    offset = request.args.get('offset', default=0, type=int)
    
    email = models.get_next_unread_email(offset) # offsetを渡す
    if email:
        return jsonify(email)
    else:
        return jsonify(None), 404

if __name__ == '__main__':
    # DB初期化確認
    models.init_db()
    app.run(debug=True, port=5002)
