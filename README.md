# SNS

## GmailAPI取得方法
1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成。
2. 「APIとサービス」→「ライブラリ」で Gmail API を検索して有効化。
3. 「OAuth同意画面」を作成（User Typeは「外部」、テストユーザーに自分のGmailアドレスを追加）。
4. 「認証情報」→「認証情報を作成」→「OAuthクライアントID」→「デスクトップアプリ」を選択して作成。
5. credentials.json をダウンロードし、backend/credentials/フォルダに置く。

## Azure Portalの取得方法
1. [Azure Portal](https://www.google.com/search?q=https://portal.azure.com/)にログインし「Microsoft Entra ID」を開きます。
2. 左メニューの「アプリの登録」→「新規登録」をクリック。
3. サポートされているアカウントの種類: 「個人の Microsoft アカウントのみ」
4. リダイレクト URI: 選択肢から「パブリック クライアント/ネイティブ...」を選び、右の欄に http://localhost と入力して「登録」をクリック。
5. 作成されたアプリの「概要」ページにある「アプリケーション (クライアント) ID」をコピーします。
6. VS Codeなどで backend/credentials/outlook_credentials.json というファイルを新規作成し、以下の内容で保存してください。
```JSON
{
    "client_id": "ここにコピーしたクライアントIDを貼り付け"
}
```
### ライブラリのインストール
`pip install msal requests`