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

## IMAPの使い方
1. backend\credentials\imap_credentials.jsonを作成
* 1つの場合
```json
[
    {
        "host": "imap.mail.yahoo.co.jp",
        "port": 993,
        "username": "自分のメールアドレス@yahoo.co.jp",
        "password": "自分のアカウントのパスワード"
    }
]
```
* 2つの場合
```json
[
    {
        "host": "imap.mail.yahoo.co.jp",
        "port": 993,
        "username": "自分のメールアドレス@yahoo.co.jp",
        "password": "自分のアカウントのパスワード"
    },
    {
    "host": "imap.mail.me.com",
    "port": 993,
    "username": "自分のメールアドレス@icloud.com",
    "password": "App用パスワード"
    }
]
```

### 注意点
1. [Apple IDの管理サイト](https://www.google.com/search?q=https://appleid.apple.com/) にログイン。

2. 「サインインとセキュリティ」→「App用パスワード」を選択。

3. 「+」ボタン（または「App用パスワードを生成」）を押し、適当な名前（例: PythonApp）を入力。

4. 表示された xxxx-xxxx-xxxx-xxxx 形式の文字列を、このJSONの "password" 欄に貼り付けます（ハイフンはあってもなくても通ることが多いですが、そのままコピペで大丈夫です）。

のように普通のパスワードだと不可能な場合もあり

### ライブラリのインストール
`pip3 install -r requirements.txt`

## ファイル構成
```Plaintext
SNS_notification/
├── .gitignore
├── README.md
├── requirements.txt
├── frontend/                  
│   └── index.html
└── backend/                   
    ├── credentials/          
    │   ├── gmail_credentials.json
    │   ├── gmail_token.json
    │   ├── imap_credentials.json
    │   ├── outlook_credentials.json
    │   └── outlook_token.json
    ├── db/                   
    │   └── emails.db
    └── src/                   
        ├── app.py             # Flaskサーバー
        ├── models.py          # データベース操作
        ├── gmail_fetcher.py   # Gmail取得
        ├── imap_fetcher.py    # Yahoo/iCloud等取得
        └── outlook_fetcher.py # Outlook取得
```

## 実行方法
### メールの読み込み
`backend\src\gmail_fetcher.py`
`backend\src\imap_fetcher.py`
`backend\src\outlook_fetcher.py`
のいずれか最低1個を実行

### バックエンドの実行
`backend\src\app.py`
を実行

### ローカルサイトにアクセス
http://localhost:5002/