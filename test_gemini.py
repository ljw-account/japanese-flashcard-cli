import os
from dotenv import load_dotenv

# 引入最新版的 google-genai 套件
from google import genai
from google.genai import types

# ==========================================
# 1. 系統初始化與設定
# ==========================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("嚴重錯誤：找不到 GEMINI_API_KEY 環境變數！")
    exit(1)

# 初始化新版的 Client 客戶端
client = genai.Client(api_key=api_key)

# 統一的系統人設與規則（全域變數）
SYSTEM_RULES = """
你是一個嚴格但溫柔的日文家教機器人。請絕對遵守以下規則：
1. 【零廢話】：絕對禁止輸出開場白、結語或任何客套話，直接給出最終內容。
2. 【標音規則】：文章中的 N5、N4 常見漢字不標音；N3（含）以上難度或不常見的漢字，必須在後方用半形括號標註平假名，例如：躊躇(ちゅうちょ)。
"""

# ==========================================
# 2. 核心功能函式
# ==========================================

def generate_daily_lesson(topic="日常對話"):
    """
    根據給定的主題，生成 N4 程度的短文、翻譯、單字解析與開放式提問。
    """
    prompt = f"""
    請依照我指定的主題：『{topic}』，嚴格按照下方的【輸出模板】格式產生內容。
    除了模板中規定的內容外，不准新增任何其他標題、層級或多餘的解說字眼。

    【輸出模板】
    📝 **日文短文及繁體中文翻譯**
    (在此填入 3~4 句 N4 程度的短文，並遵守漢字標音規則)
    (在此填入上述短文的繁體中文翻譯)

    📖 **單字解析**
    1. [單字1] ([平假名]) - [中文意思]
    2. [單字2] ([平假名]) - [中文意思]
    3.[單字3] ([平假名]) - [中文意思]

    💬 **老師的提問**
    (在此填入一個沒有標準答案的開放式日文問題)
    """
    
    try:
        # 新版 SDK 的呼叫寫法
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_RULES,
            )
        )
        return response.text
    except Exception as e:
        print(f"[API 錯誤 - generate_daily_lesson]: {e}")
        return "不好意思，老師現在有點頭暈（系統連線異常），請稍後再試一次喔！"


def grade_answer(question, user_answer):
    """
    接收老師先前的提問與學生的回答，進行邏輯與文法批改。
    """
    prompt = f"""
    老師之前的提問：{question}
    學生的日文回答：{user_answer}

    請根據以上資訊進行批改。
    任務要求：
    1. 分析學生的回答是否符合問題邏輯。
    2. 檢查文法、單字使用是否正確。
    3. 如果有錯，請給出【正確的日文寫法】並用中文解釋錯誤原因。
    4. 如果完全正確，請給予簡短的日文稱讚。
    5. 最後，用一句話溫柔地鼓勵學生。
    
    請嚴格遵守系統設定的【零廢話】與【漢字標音】規則，直接輸出批改內容。
    """
    
    try:
        # 新版 SDK 的呼叫寫法
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_RULES,
            )
        )
        return response.text
    except Exception as e:
        print(f"[API 錯誤 - grade_answer]: {e}")
        return "不好意思，老師的批改紅筆突然沒水了（系統連線異常），請稍後再傳送一次你的答案！"

if __name__ == "__main__":
    print("--- 測試最新版 SDK 函式 ---")
    lesson = generate_daily_lesson(topic="在日本搭電車")
    print(lesson)