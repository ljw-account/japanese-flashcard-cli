import os
import json
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from flask import Flask, request, abort

import firebase_admin
from firebase_admin import credentials, firestore
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
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)

# 1. 環境變數與連線
load_dotenv()
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
firebase_cred_str = os.getenv('FIREBASE_CREDENTIALS')

if not channel_secret or not channel_access_token or not firebase_cred_str:
    print("啟動失敗：找不到環境變數！")
    exit(1)

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

# 2. 從雲端載入單字庫
vocab_dict = {}
try:
    docs = db.collection('vocabulary').stream()
    for doc in docs:
        data = doc.to_dict()
        vocab_dict[data['word']] = data['meaning']
    print(f"✅ 已從雲端載入 {len(vocab_dict)} 個單字。")
except Exception as e:
    print(f"❌ 讀取雲端單字庫失敗: {e}")

# 3. 初始化 Flask 與 LINE
app = Flask(__name__)
handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

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

# ==========================================
# 工具函式：發送閃卡 (注意：上面沒有 decorator)
# ==========================================
def send_flashcard(reply_token):
    if not vocab_dict:
        msg = TextMessage(text="單字庫目前是空的，請先去 Firebase 新增單字！")
    else:
        word = random.choice(list(vocab_dict.keys()))
        msg = TemplateMessage(
            alt_text=f"單字卡：{word}",
            template=ButtonsTemplate(
                title=f"🇯🇵 {word}",
                text="請回想中文意思...",
                actions=[
                    PostbackAction(
                        label="👀 看答案",
                        data=f"action=show_answer&word={word}"
                    )
                ]
            )
        )
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[msg]
            )
        )

# ==========================================
# 處理「文字」訊息
# ==========================================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    reply_text = ""

    user_ref = db.collection('users').document(user_id)
    tz_tpe = timezone(timedelta(hours=8))
    today_str = datetime.now(tz_tpe).strftime("%Y-%m-%d")

    if user_text == '今日新聞':
        lesson_doc = db.collection('daily_lessons').document(today_str).get()
        if lesson_doc.exists:
            lesson_content = lesson_doc.to_dict().get('lesson_content', '找不到內容')
            user_ref.set({'mode': 'daily_news', 'context': lesson_content})
            reply_text = f"📰 幫你準備好今天的日文新聞囉！\n\n{lesson_content}"
        else:
            reply_text = f"今天的教材 ({today_str}) 還沒準備好喔！"

    elif user_text in ['背單字', '抽考']:
        # 呼叫閃卡工具，只傳入字串 token
        send_flashcard(event.reply_token)
        return

    else:
        user_doc = user_ref.get()
        if user_doc.exists:
            state_data = user_doc.to_dict()
            mode = state_data.get('mode', '')
            if mode == 'daily_news':
                context = state_data.get('context', '')
                reply_text = grade_answer(question=context, user_answer=user_text)
                user_ref.delete()
            else:
                reply_text = "你目前在未知的答題模式中，已為你重置狀態。"
                user_ref.delete()
        else:
            reply_text = "將軍您好！\n請點擊選單，或輸入「今日新聞」、「背單字」來進行學習！"

    if reply_text:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )

# ==========================================
# 處理「按鈕」訊息 (無限閃卡流)
# ==========================================
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    params = dict(item.split('=') for item in data.split('&'))
    action = params.get('action')
    word = params.get('word')
    user_id = event.source.user_id

    reply_msgs =[]

    if action == 'show_answer':
        meaning = vocab_dict.get(word, "找不到翻譯")
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

    elif action in ['result_good', 'result_bad']:
        if action == 'result_bad':
            meaning = vocab_dict.get(word)
            if meaning:
                db.collection('mistakes').document(user_id).set({word: meaning}, merge=True)

        if vocab_dict:
            next_word = random.choice(list(vocab_dict.keys()))
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

    if reply_msgs:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=reply_msgs
                )
            )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)