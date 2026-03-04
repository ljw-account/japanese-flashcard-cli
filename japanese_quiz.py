import random
import json
import os

def load_words(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        vocab_dict = json.load(file)
    return vocab_dict

def save_mistakes(mistakes_dict, file_path):
    if mistakes_dict:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(mistakes_dict, file, ensure_ascii=False, indent=4)

def run_quiz(vocab_dict):
    score = 0
    question =0
    mistakes = {}

    while True:
        random_vocab = random.choice(list(vocab_dict.keys()))

        print(f"{random_vocab}的中文是什麼")
        answer = input()
        if (answer == 'q'):
            break
        question += 1
        if (answer == vocab_dict[random_vocab]):
            print("正確")
            score += 1
        else:
            print(f"答錯! 正確答案是 {vocab_dict[random_vocab]}")
            mistakes[random_vocab] = vocab_dict[random_vocab]

    if question > 0:
        win_percentage = round(100*score/question)
        print(f"測驗結束! 你總共回答 {question} 題, 答對 {score} 題, 正確率為 {win_percentage}%")
    else:
        print("測驗結束! 你沒有回答任何問題。")
    return mistakes

if __name__ == "__main__":
    vocab_file_path = 'd:/python/restart_python/japanese_vocab.json'
    mistake_file_path = 'd:/python/restart_python/mistakes.json'
    print("歡迎來到日文閃卡機！請選擇模式：")
    print("輸入[1] 測驗全部單字 ")
    print("輸入[2] 複習錯題本 ")
    choice = input().strip()

    if choice == '1':
        my_vocab = load_words(vocab_file_path)
        my_mistakes = run_quiz(my_vocab)
        save_mistakes(my_mistakes, mistake_file_path)
    elif choice == '2':
        if os.path.exists(mistake_file_path):
            my_vocab = load_words(mistake_file_path)
            my_mistakes = run_quiz(my_vocab)
            save_mistakes(my_mistakes, mistake_file_path)
        else:
            print("目前沒有錯題本紀錄喔！請先選擇 [1] 進行測驗。")
    else:
        print("請輸入[1]或[2]")

