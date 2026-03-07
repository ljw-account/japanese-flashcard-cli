import os
import json
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. 初始化設定
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# 設定單字庫檔案路徑
VOCAB_FILE = 'japanese_vocab.json'

def generate_vocab_list(level="N4", count=30, topic="日常與旅遊"):
    """
    呼叫 AI 生成指定程度與主題的單字
    """
    print(f"🤖 正在請求 AI 生成 {count} 個 {level} 程度的單字 (主題：{topic})...")
    
    prompt = f"""
    請生成 {count} 個 JLPT {level} 程度的日文單字，主題專注於「{topic}」。
    
    【格式嚴格要求】
    請直接回傳一個標準的 JSON 格式字串，不要有任何 markdown 標記 (如 ```json)。
    格式為 key-value pair，Key 是日文單字(含平假名)，Value 是中文意思。
    
    範例格式：
    {{
        "食べる(たべる)": "吃",
        "歩く(あるく)": "走路",
        "駅(えき)": "車站"
    }}
    
    請確保生成的 JSON 格式合法。
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json" # 強制 AI 回傳 JSON 格式
            )
        )
        return response.text
    except Exception as e:
        print(f"❌ AI 生成失敗: {e}")
        return "{}"

def save_to_json(new_vocab_str):
    """
    將生成的單字合併進現有的 json 檔案
    """
    try:
        # 1. 解析 AI 回傳的字串為字典
        new_vocab_dict = json.loads(new_vocab_str)
        print(f"✅ AI 成功生產了 {len(new_vocab_dict)} 個新單字！")

        # 2. 讀取舊的單字庫 (如果存在)
        if os.path.exists(VOCAB_FILE):
            with open(VOCAB_FILE, 'r', encoding='utf-8') as f:
                try:
                    existing_vocab = json.load(f)
                except json.JSONDecodeError:
                    existing_vocab = {}
        else:
            existing_vocab = {}

        # 3. 合併字典 (新單字加入舊單字庫)
        # update 方法會自動去重 (如果 Key 一樣會覆蓋)
        existing_vocab.update(new_vocab_dict)

        # 4. 寫回檔案
        with open(VOCAB_FILE, 'w', encoding='utf-8') as f:
            # ensure_ascii=False 才能正常顯示中文，indent=4 讓格式漂亮
            json.dump(existing_vocab, f, ensure_ascii=False, indent=4)
            
        print(f"💾 存檔完成！目前單字庫總共有 {len(existing_vocab)} 個單字。")
        print(f"📂 檔案位置：{VOCAB_FILE}")

    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗，AI 回傳的可能不是標準格式: {e}")
        print("回傳內容:", new_vocab_str)

if __name__ == "__main__":
    # 你可以在這裡修改想要生成的等級和主題
    generate_vocab_list(level="N4", count=50, topic="生活與職場")
    
    # 把 AI 回傳的字串存入檔案
    # 注意：generate_vocab_list 回傳的是字串，save_to_json 負責解析
    # 這裡我們稍微修改一下流程，讓 generate_vocab_list 直接回傳字串給 save_to_json
    
    # 重新執行一次正確的流程：
    json_str = generate_vocab_list(level="N4", count=50, topic="生活與職場")
    save_to_json(json_str)