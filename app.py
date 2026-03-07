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
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    PostbackAction
)
from linebot.v3.webhooks import PostbackEvent
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
# 3. [升級] 從 Firebase 讀取單字庫
# 注意：這會在伺服器啟動時執行一次。如果單字庫非常大(破萬)，建議改用其他隨機抽取策略。
vocab_dict = {}
try:
    docs = db.collection('vocabulary').stream()
    for doc in docs:
        data = doc.to_dict()
        # 格式轉換回原本的 key:value 結構
        vocab_dict[data['word']] = data['meaning']
    print(f"✅ 已從雲端載入 {len(vocab_dict)} 個單字。")
except Exception as e:
    print(f"❌ 讀取雲端單字庫失敗: {e}")

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
def send_flashcard(reply_token):
    """
    核心邏輯：隨機抽一個單字，並傳送「問題卡片（按鈕）」給使用者
    """
    # 這裡我們需要全域變數 db 和 vocab_dict
    # 為了避免變數範圍問題，我們直接使用全域的
    global vocab_dict

    if not vocab_dict:
        # 如果單字庫是空的
        # 注意：這裡不能直接回傳 TextMessage 物件，因為它只是物件，要包在 ReplyMessageRequest 裡發送
        # 但為了簡化，我們先發送一個簡單的文字
        msg = TextMessage(text="單字庫目前是空的，請先去 Firebase 新增單字！")
    else:
        # 1. 隨機抽字
        word = random.choice(list(vocab_dict.keys()))
        
        # 2. 製作「按鈕樣板消息」 (修正為 TemplateMessage)
        msg = TemplateMessage(
            alt_text=f"單字卡：{word}",
            template=ButtonsTemplate(
                title=f"🇯🇵 {word}",
                text="請回想中文意思...",
                actions=[
                    # 當使用者按這個按鈕，LINE 會偷偷傳送 data 給後端
                    PostbackAction(
                        label="👀 看答案",
                        data=f"action=show_answer&word={word}"
                    )
                ]
            )
        )

    # 3. 發送訊息
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[msg]
            )
        )
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
    # ... 前面的今日新聞邏輯 ...
    
    # 模式 B：進入「Anki 閃卡」模式 (取代原本的抽考，或並存)
    elif user_text == '背單字' or user_text == '抽考':
        send_flashcard(event.reply_token) # 移除了 user_id 參數，因為函式內沒用到
        return 

    # ... 後面的邏輯 ...

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

@handler.add(PostbackEvent)
def handle_postback(event):
    # 解析回傳的 data
    data = event.postback.data
    params = dict(item.split('=') for item in data.split('&'))
    action = params.get('action')
    word = params.get('word')
    user_id = event.source.user_id # 取得 User ID 用來存錯題

    reply_msgs = []

    # 情境 A：使用者點了「看答案」
    if action == 'show_answer':
        meaning = vocab_dict.get(word, "找不到翻譯")
        
        # 製作「答案卡片」 (修正為 TemplateMessage)
        reply_msgs.append(TemplateMessage(
            alt_text=f"答案：{meaning}",
            template=ButtonsTemplate(
                title=f"中文：{meaning}",
                text=f"日文：{word}\n你剛才記對了嗎？",
                actions=[
                    PostbackAction(label="✅ 記得", data=f"action=result_good&word={word}"),
                    PostbackAction(label="❌ 忘了", data=f"action=result_bad&word={word}")
                ]
            )
        ))

    # 情境 B：使用者評分（記得/忘了） -> 紀錄後直接下一題
    elif action in ['result_good', 'result_bad']:
        # 如果是「忘了」，存入錯題本
        if action == 'result_bad':
            meaning = vocab_dict.get(word)
            if meaning:
                db.collection('mistakes').document(user_id).set({word: meaning}, merge=True)

        # 🔥 重點：直接產生下一張閃卡
        next_word = random.choice(list(vocab_dict.keys()))
        
        # 製作下一張題目卡 (修正為 TemplateMessage)
        next_card = TemplateMessage(
            alt_text=f"單字卡：{next_word}",
            template=ButtonsTemplate(
                title=f"🇯🇵 {next_word}",
                text="下一題！請回想中文意思...",
                actions=[
                    PostbackAction(
                        label="👀 看答案",
                        data=f"action=show_answer&word={next_word}"
                    )
                ]
            )
        )
        reply_msgs.append(next_card)

    # 統一發送回覆
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=reply_msgs
            )
        )

if __name__ == "__main__":
    # 從環境變數抓取 Render 分配的 Port，如果沒有就預設 5000
    port = int(os.environ.get('PORT', 5000))
    # host='0.0.0.0' 就是強制打開外網大門的關鍵！
    app.run(host='0.0.0.0', port=port)