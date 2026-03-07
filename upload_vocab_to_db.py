import json
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# 1. 初始化 Firebase (複製你熟悉的寫法)
load_dotenv()
firebase_cred_str = os.getenv('FIREBASE_CREDENTIALS')

if not firebase_cred_str:
    print("❌ 找不到 FIREBASE_CREDENTIALS，請檢查 .env")
    exit(1)

try:
    cred_dict = json.loads(firebase_cred_str)
    if 'private_key' in cred_dict:
        cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"❌ Firebase 連線失敗: {e}")
    exit(1)

# 2. 讀取本地 JSON
VOCAB_FILE = 'japanese_vocab.json'
try:
    with open(VOCAB_FILE, 'r', encoding='utf-8') as f:
        vocab_dict = json.load(f)
    print(f"📖 讀取到 {len(vocab_dict)} 個本地單字。")
except FileNotFoundError:
    print("❌ 找不到 json 檔案！")
    exit(1)

# 3. 批次寫入 Firebase
print("🚀 開始上傳到雲端 (集合: vocabulary)...")
batch = db.batch()
count = 0

for japanese, chinese in vocab_dict.items():
    # 使用日文當作 Document ID，這樣就不會重複新增
    doc_ref = db.collection('vocabulary').document(japanese)
    batch.set(doc_ref, {'word': japanese, 'meaning': chinese})
    count += 1
    
    # Firebase batch 一次最多 500 筆，超過要先 commit
    if count % 400 == 0:
        batch.commit()
        batch = db.batch()
        print(f"已上傳 {count} 筆...")

# 剩下不足 400 筆的最後一次提交
batch.commit()
print(f"🎉 全部上傳完成！共 {count} 個單字已進入 Firebase。")