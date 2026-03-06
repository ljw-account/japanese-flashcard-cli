import os
import json
import random
from dotenv import load_dotenv
from flask import Flask, request, abort

# --- 引入 Firebase Admin 套件 ---
import firebase_admin
from firebase_admin import credentials, firestore

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

# 1. 讀取環境變數
load_dotenv()
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if not channel_secret or not channel_access_token:
    print("讀取失敗！請檢查 .env 檔案與變數名稱設定。")
    exit(1)

# 2. 初始化 Firebase Firestore 客戶端
# 請確認 japanese_firebasekey.json 檔案與此 app.py 放在同一個資料夾下
# 2. 初始化 Firebase Firestore 客戶端 (環境變數版)
firebase_cred_str = os.getenv('FIREBASE_CREDENTIALS')

if not firebase_cred_str:
    print("啟動失敗：找不到 FIREBASE_CREDENTIALS 環境變數！")
    exit(1)

try:
    # A. 將字串解析為 Python 字典
    firebase_cred_dict = json.loads(firebase_cred_str)
    
    # B. 【關鍵防呆】處理 private_key 中的換行符號問題
    # 將可能被雲端平台錯誤轉義的 "\\n" (兩個字元)，強制替換回真實的 "\n" (換行符號)
    if 'private_key' in firebase_cred_dict:
        firebase_cred_dict['private_key'] = firebase_cred_dict['private_key'].replace('\\n', '\n')

    # C. 使用整理好的字典初始化 Certificate，而不是傳入檔案路徑
    cred = credentials.Certificate(firebase_cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase 雲端資料庫連線成功！")
    
except json.JSONDecodeError as e:
    print(f"Firebase JSON 格式解析失敗，請確認貼上的內容是否完整：{e}")
    exit(1)
except Exception as e:
    print(f"Firebase 初始化發生未預期錯誤：{e}")
    exit(1)

# 3. 讀取本地端單字庫
vocab_file_path = 'japanese_vocab.json'
try:
    with open(vocab_file_path, 'r', encoding='utf-8') as file:
        vocab_dict = json.load(file)
except FileNotFoundError:
    print(f"找不到單字庫：{vocab_file_path}，請確認檔案位置！")
    vocab_dict = {}

app = Flask(__name__)
handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

# [新增] 健康檢查路由，專門給 Uptime Monitor 敲門用，不會干擾 LINE 機器人運作
@app.route("/ping", methods=['GET'])
def ping():
    return "pong", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 4. 訊息處理核心邏輯 (雲端資料庫版)
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    reply_text = ""

    # 設定 Firestore 的文件參照 (Reference)
    # user_ref 指向 users 集合中，名為該 user_id 的文件
    user_ref = db.collection('users').document(user_id)

    # 邏輯 A：使用者要求開始抽考
    if user_text == '抽考':
        if not vocab_dict:
            reply_text = "目前單字庫是空的或發生錯誤，無法測驗！"
        else:
            # 隨機抽出一個日文單字與對應的中文
            random_vocab = random.choice(list(vocab_dict.keys()))
            correct_answer = vocab_dict[random_vocab]
            
            # 【雲端寫入】將考試狀態寫入 Firestore
            # 我們同時記錄 question (日文) 與 correct_answer (中文)
            user_ref.set({
                'question': random_vocab,
                'correct_answer': correct_answer
            })
            
            reply_text = f"請問【{random_vocab}】的中文是什麼？"

    # 邏輯 B：使用者輸入其他文字 (檢查是否在答題)
    else:
        # 【雲端讀取】去資料庫抓取這個使用者的狀態
        user_doc = user_ref.get()
        
        # 檢查該文件是否存在 (代表他正在答題階段)
        if user_doc.exists:
            # 取出資料庫裡的題目與正確答案
            state_data = user_doc.to_dict()
            question = state_data.get('question')
            correct_answer = state_data.get('correct_answer')
            
            # 比對答案
            if user_text == correct_answer:
                reply_text = "答對了！"
            else:
                reply_text = f"答錯了，正確答案是 {correct_answer}"
                
                # 【雲端寫入錯題本】
                # mistakes_ref 指向 mistakes 集合中，名為該 user_id 的文件
                mistakes_ref = db.collection('mistakes').document(user_id)
                # 使用 merge=True 的好處是：如果文件不存在會自動建立；
                # 如果已經存在，它會把新的錯題「合併」進去，且遇到重複的單字會自動覆蓋，不會產生重複紀錄
                mistakes_ref.set({
                    question: correct_answer
                }, merge=True)
            
            # 【雲端刪除】答題結束，刪除該使用者的考試狀態，讓他離開答題模式
            user_ref.delete()
            
        else:
            # 資料庫找不到他的狀態，代表他還沒開始測驗
            reply_text = "請輸入「抽考」來開始測驗！"

    # 5. 呼叫 LINE API 傳送回覆
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

if __name__ == "__main__":
    app.run(port=5000, debug=True)