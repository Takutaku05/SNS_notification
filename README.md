# SNS

## GmailAPI取得方法
1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成。
2. 「APIとサービス」→「ライブラリ」で Gmail API を検索して有効化。
3. 「OAuth同意画面」を作成（User Typeは「外部」、テストユーザーに自分のGmailアドレスを追加）。
4. 「認証情報」→「認証情報を作成」→「OAuthクライアントID」→「デスクトップアプリ」を選択して作成。
5. credentials.json をダウンロードし、backend/credentials/フォルダに置く。