import random
import json

with open('d:/python/restart_python/japanese_vocab.json', 'r', encoding='utf-8') as file:
    vocab_dict = json.load(file)
score = 0
question =0

while True:
    random_vocab = random.choice(list(vocab_dict.keys()))

    print(f"What is the Chinese of {random_vocab}")
    answer = input()
    if (answer == 'q'):
        break
    question += 1
    if (answer == vocab_dict[random_vocab]):
        print("Correct")
        score += 1
    else:
        print(f"Wrong, the correct answer is {vocab_dict[random_vocab]}")

if question > 0:
    win_percentage = round(100*score/question)
    print(f"The test is over! You total answer {question} questions, score {score} questions, win percentage is {win_percentage}%")
else:
    [print("The test is over! You didn't answer any questions.")]
