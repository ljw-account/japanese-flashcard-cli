import os
import json
import random
# 引入時間與時區模組 (解決雲端時區問題)
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from flask import Flask, request, abort

# 引入 Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# 【新增】引入你的 AI 導師批改模組
from test_gemini import grade_answer

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
firebase_cred_str = os.getenv('FIREBASE_CREDENTIALS')

if not channel_secret or not channel_access_token or not firebase_cred_str:
    print("啟動失敗：找不到環境變數！")
    exit(1)

# 2. 初始化 Firebase
try:
    firebase_cred_dict = json.loads(firebase_cred_str)
    if 'private_key' in firebase_cred_dict:
        firebase_cred_dict['private_key'] = firebase_cred_dict['private_key'].replace('\\n', '\n')

    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_cred_dict)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Firebase 初始化錯誤：{e}")
    exit(1)

# 3. 讀取本地端單字庫 (給舊的抽考功能用)
vocab_file_path = 'japanese_vocab.json'
try:
    with open(vocab_file_path, 'r', encoding='utf-8') as file:
        vocab_dict = json.load(file)
except FileNotFoundError:
    vocab_dict = {}

app = Flask(__name__)
handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

# Uptime Monitor 健康檢查
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

# 4. 訊息處理核心邏輯 (雙模式切換)
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    reply_text = ""

    user_ref = db.collection('users').document(user_id)
    
    # 建立台北時區 (UTC+8)
    tz_tpe = timezone(timedelta(hours=8))
    today_str = datetime.now(tz_tpe).strftime("%Y-%m-%d")

    # ==========================================
    # 模式 A：進入「每日讀報」模式
    # ==========================================
    if user_text == '今日新聞':
        # 去 daily_lessons 抓今天的教材
        lesson_doc = db.collection('daily_lessons').document(today_str).get()
        
        if lesson_doc.exists:
            lesson_content = lesson_doc.to_dict().get('lesson_content', '找不到內容')
            
            # 【狀態切換】將使用者狀態設為 daily_news，並把整篇教材當作上下文存起來
            user_ref.set({
                'mode': 'daily_news',
                'context': lesson_content
            })
            reply_text = f"📰 幫你準備好今天的日文新聞囉！\n\n{lesson_content}"
        else:
            reply_text = f"今天的教材 ({today_str}) 還沒準備好喔！請確認深夜印報機是否正常運作。"

    # ==========================================
    # 模式 B：進入原本的「單字抽考」模式
    # ==========================================
    elif user_text == '抽考':
        if not vocab_dict:
            reply_text = "目前單字庫是空的！"
        else:
            random_vocab = random.choice(list(vocab_dict.keys()))
            correct_answer = vocab_dict[random_vocab]
            
            # 【狀態切換】將使用者狀態設為 vocab
            user_ref.set({
                'mode': 'vocab',
                'question': random_vocab,
                'correct_answer': correct_answer
            })
            reply_text = f"請問【{random_vocab}】的中文是什麼？"

    # ==========================================
    # 模式 C：使用者回答問題 (系統根據狀態自動批改)
    # ==========================================
    else:
        user_doc = user_ref.get()
        
        if user_doc.exists:
            state_data = user_doc.to_dict()
            mode = state_data.get('mode', 'vocab') # 預設相容舊版
            
            # 處理單字抽考的回答
            if mode == 'vocab':
                correct_answer = state_data.get('correct_answer')
                question = state_data.get('question')
                if user_text == correct_answer:
                    reply_text = "答對了！🎉"
                else:
                    reply_text = f"答錯了，正確答案是 {correct_answer} 😢"
                    db.collection('mistakes').document(user_id).set({question: correct_answer}, merge=True)
                user_ref.delete()
                
            # 處理 AI 讀報的回答
            elif mode == 'daily_news':
                context = state_data.get('context', '')
                
                # 💡 呼叫 Gemini AI 導師進行批改！(這可能會花 2~5 秒)
                reply_text = grade_answer(question=context, user_answer=user_text)
                
                # 批改完畢，解除答題狀態
                user_ref.delete()
        else:
            # 找不到狀態，代表不在任何測驗中
            reply_text = "將軍您好！\n請輸入「今日新聞」來獲取最新的時事閱讀測驗，\n或輸入「抽考」來複習單字！"

    # 5. 回傳訊息給 LINE
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