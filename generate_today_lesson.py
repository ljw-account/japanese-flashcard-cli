import os
import json
from datetime import datetime
from dotenv import load_dotenv

# 引入 Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# 引入你寫好的兩個強大模組！
from news_crawler import fetch_latest_yahoo_news_full
from test_gemini import generate_daily_lesson

def main():
    print("🚀 啟動【每日派報系統】資料管線...")
    
    # ==========================================
    # 1. 載入環境變數與連線 Firebase
    # (完美複製你 app.py 中的安全連線寫法)
    # ==========================================
    load_dotenv()
    firebase_cred_str = os.getenv('FIREBASE_CREDENTIALS')
    
    if not firebase_cred_str:
        print("❌ 找不到 FIREBASE_CREDENTIALS 環境變數！")
        return

    try:
        firebase_cred_dict = json.loads(firebase_cred_str)
        if 'private_key' in firebase_cred_dict:
            firebase_cred_dict['private_key'] = firebase_cred_dict['private_key'].replace('\\n', '\n')
            
        # 確保不會重複初始化 (在獨立腳本中很安全)
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_cred_dict)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase 連線成功！")
    except Exception as e:
        print(f"❌ Firebase 初始化發生錯誤：{e}")
        return

    # ==========================================
    # 2. 取得今天的日期字串 (格式：YYYY-MM-DD)
    # ==========================================
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"📅 今天的日期是：{today_str}")

    # ==========================================
    # 3. 執行檢索 (R) - 情報官抓新聞
    # ==========================================
    print("\n📰 正在派遣情報官去 Yahoo 抓取最新新聞...")
    news_text = fetch_latest_yahoo_news_full()
    
    # 簡單防呆：如果回傳的字串包含錯誤訊息就停止
    if "發生錯誤" in news_text or "無法" in news_text:
        print(f"❌ 抓取新聞失敗：\n{news_text}")
        return
    print("✅ 新聞抓取成功！")

    # ==========================================
    # 4. 增強生成 (G) - 呼叫 AI 導師編寫教材
    # ==========================================
    print("\n🧠 正在將新聞交給 AI 導師編寫今日教材 (約需 5~10 秒)...")
    
    # 【關鍵串接】把抓到的新聞當作 topic 餵給 Gemini！
    prompt_topic = f"請根據這篇真實的日本新聞來編寫教材：\n\n{news_text}"
    daily_lesson = generate_daily_lesson(topic=prompt_topic)
    
    if "系統連線異常" in daily_lesson:
        print("❌ AI 生成教材失敗！")
        return
    print("✅ 教材生成成功！")

    # ==========================================
    # 5. 存入雲端大腦 (Load to Firebase)
    # ==========================================
    print("\n☁️ 正在將教材存入 Firebase 的 [daily_lessons] 集合...")
    
    # 指向 daily_lessons 集合中，名為今天日期 (例如 2026-03-07) 的文件
    lesson_ref = db.collection('daily_lessons').document(today_str)
    
    # 將生成的內容寫入資料庫
    lesson_ref.set({
        'date': today_str,
        'original_news': news_text,    # 順便把原文存起來，以後可以對照
        'lesson_content': daily_lesson, # 這是 AI 生成的排版教材
        'created_at': firestore.SERVER_TIMESTAMP # 記錄寫入的時間
    })
    
    print(f"🎉 任務圓滿完成！{today_str} 的教材已經上傳到雲端大腦了！")

if __name__ == "__main__":
    main()