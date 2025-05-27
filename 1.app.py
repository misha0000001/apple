from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import re
import openai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
openai.api_key = os.getenv("OPENAI_API_KEY")

activity_factors = {
    '輕度': 1.375,
    '中等': 1.55,
    '重度': 1.725
}

user_temp_data = {}  # 簡單記憶用戶輸入狀態（開發測試用途）

def parse_user_input(text):
    match = re.match(r'(男|女),\s*(\d+)歲,\s*(\d+),\s*(\d+),\s*(輕度|中等|重度)', text)
    if not match:
        return None
    gender, age, height, weight, activity = match.groups()
    return {
        'gender': gender,
        'age': int(age),
        'height': int(height),
        'weight': int(weight),
        'activity': activity
    }

def calculate_bmi(weight, height_cm):
    height_m = height_cm / 100
    return round(weight / (height_m ** 2), 2)

def calculate_bmr(gender, weight, height, age):
    if gender == '男':
        return round(66 + (13.7 * weight) + (5 * height) - (6.8 * age))
    else:
        return round(655 + (9.6 * weight) + (1.8 * height) - (4.7 * age))

def calculate_tdee(bmr, activity_level):
    factor = activity_factors.get(activity_level, 1.55)
    return round(bmr * factor)

def generate_personal_advice(user_data, bmi, bmr, tdee, goal):
    prompt = f"""
使用者基本資料如下：
- 性別：{user_data['gender']}
- 年齡：{user_data['age']}
- 身高：{user_data['height']} cm
- 體重：{user_data['weight']} kg
- 運動量：{user_data['activity']}
- 目標：{goal}

計算結果：
- BMI = {bmi}
- BMR = {bmr}
- TDEE = {tdee}

請你幫忙用健康顧問的語氣，為使用者提供針對這些資訊的完整建議，包括：
1. 營養（蛋白質與熱量攝取）
2. 運動（訓練頻率與內容）
3. 注意事項（避免的錯誤）

請使用口語化、親切的語氣回答，大約 100~150 字。
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )
    return response['choices'][0]['message']['content']

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    signature = request.headers['X-Line-Signature']
    try:
        handler.handle(body, signature)
    except:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    if '開始' in text:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入資料（格式：男, 21歲, 175, 70, 中等）")
        )
        return

    user_data = parse_user_input(text)
    if user_data:
        bmi = calculate_bmi(user_data['weight'], user_data['height'])
        bmr = calculate_bmr(user_data['gender'], user_data['weight'], user_data['height'], user_data['age'])
        tdee = calculate_tdee(bmr, user_data['activity'])

        # 暫存使用者資料
        user_temp_data[user_id] = {
            "user_data": user_data,
            "bmi": bmi,
            "bmr": bmr,
            "tdee": tdee
        }

        reply = (
            f"✅ 你的 BMI：{bmi}\n"
            f"✅ BMR：{bmr} 大卡\n"
            f"✅ TDEE：{tdee} 大卡\n\n"
            f"請問你的目標是：\n1️⃣ 增肌\n2️⃣ 減脂\n3️⃣ 維持\n請輸入數字或文字～"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 接收使用者選擇目標
    if text in ['1', '增肌']:
        goal = '增肌'
    elif text in ['2', '減脂']:
        goal = '減脂'
    elif text in ['3', '維持']:
        goal = '維持'
    else:
        goal = None

    if goal and user_id in user_temp_data:
        data = user_temp_data[user_id]
        advice = generate_personal_advice(data["user_data"], data["bmi"], data["bmr"], data["tdee"], goal)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=advice))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先輸入你的基本資料（例如：男, 21歲, 175, 70, 中等）"))

