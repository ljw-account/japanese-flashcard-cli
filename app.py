import os
import json
import random
from dotenv import load_dotenv
from flask import Flask, request, abort

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

# 2. 讀取單字庫 (請確認檔案名稱與路徑是否正確)
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

# 3. 建立全域變數，用來記錄使用者的狀態
# 格式預計為： { "使用者A的ID": "蘋果", "使用者B的ID": "香蕉" }
user_states = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 4. 訊息處理核心邏輯
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # 取得發送訊息的使用者 ID 與文字內容 (.strip() 幫助去除前後多餘空白)
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    
    # 準備用來回覆的空字串
    reply_text = ""

    # 邏輯 A：使用者要求開始抽考
    if user_text == '抽考':
        if not vocab_dict:
            reply_text = "目前單字庫是空的或發生錯誤，無法測驗！"
        else:
            # 隨機抽出一個日文單字
            random_vocab = random.choice(list(vocab_dict.keys()))
            
            # 【關鍵】把正確的中文答案存進 user_states，並綁定這個使用者的 ID
            user_states[user_id] = vocab_dict[random_vocab]
            
            # 設定要回覆的題目
            reply_text = f"請問【{random_vocab}】的中文是什麼？"

    # 邏輯 B：使用者輸入其他文字 (可能是在答題，也可能是在亂聊)
    else:
        # 檢查這個 user_id 是否在 user_states 裡面 (代表他正在答題階段)
        if user_id in user_states:
            # 取出我們先前幫他存好的正確答案
            correct_answer = user_states[user_id]
            
            # 比對答案
            if user_text == correct_answer:
                reply_text = "答對了！"
            else:
                reply_text = f"答錯了，正確答案是 {correct_answer}"
            
            # 【關鍵】答題結束，必須把這個使用者的狀態清空，以免他卡在答題模式
            del user_states[user_id]
            
        # 如果不在 user_states 裡，代表他還沒開始測驗
        else:
            reply_text = "請輸入「抽考」來開始測驗！"

    # 5. 呼叫 LINE API 將設定好的 reply_text 傳送出去
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