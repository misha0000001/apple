import os
from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import google.generativeai as genai

# 讀取金鑰（Render 環境變數中設定）
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)

# LINE Bot 初始化
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)
messaging_api = MessagingApi(ApiClient(configuration))

user_temp_data = {}

activity_factors = {
    "低": 1.2,
    "中等": 1.55,
    "高": 1.9
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

請你用健康顧問的口吻給出建議，內容包含：
1. 飲食（蛋白質與熱量）
2. 運動（頻率與內容）
3. 錯誤習慣要避免
用親切的口語化語氣，大約 100~150 字。
"""
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini 錯誤：{type(e).__name__}")
        return "⚠️ AI 回應目前無法取得，請稍後再試 🙇‍♂️"

def parse_user_input(text):
    try:
        parts = text.replace("，", ",").split(",")
        gender = parts[0].strip()
        age = int(parts[1].replace("歲", "").strip())
        height = int(parts[2].strip())
        weight = float(parts[3].strip())
        activity = parts[4].strip()
        return {
            "gender": gender,
            "age": age,
            "height": height,
            "weight": weight,
            "activity": activity
        }
    except:
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"LINE 錯誤：{e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    if '開始' in text:
        message = TextMessage(text="請輸入資料（格式：男, 21歲, 175, 70, 中等）")
        reply = ReplyMessageRequest(reply_token=event.reply_token, messages=[message])
        messaging_api.reply_message(reply)
        return

    user_data = parse_user_input(text)
    if user_data:
        bmi = calculate_bmi(user_data['weight'], user_data['height'])
        bmr = calculate_bmr(user_data['gender'], user_data['weight'], user_data['height'], user_data['age'])
        tdee = calculate_tdee(bmr, user_data['activity'])

        user_temp_data[user_id] = {
            "user_data": user_data,
            "bmi": bmi,
            "bmr": bmr,
            "tdee": tdee
        }

        reply_text = (
            f"✅ 你的 BMI：{bmi}\n"
            f"✅ BMR：{bmr} 大卡\n"
            f"✅ TDEE：{tdee} 大卡\n\n"
            f"請問你的目標是：\n1️⃣ 增肌\n2️⃣ 減脂\n3️⃣ 維持\n請輸入數字或文字～"
        )
        message = TextMessage(text=reply_text)
        reply = ReplyMessageRequest(reply_token=event.reply_token, messages=[message])
        messaging_api.reply_message(reply)
        return

    goal = None
    if text in ['1', '增肌']:
        goal = '增肌'
    elif text in ['2', '減脂']:
        goal = '減脂'
    elif text in ['3', '維持']:
        goal = '維持'

    if goal and user_id in user_temp_data:
        data = user_temp_data[user_id]
        advice = generate_personal_advice(data["user_data"], data["bmi"], data["bmr"], data["tdee"], goal)
        message = TextMessage(text=advice)
        reply = ReplyMessageRequest(reply_token=event.reply_token, messages=[message])
        messaging_api.reply_message(reply)
    else:
        message = TextMessage(text="⚠️ 請先輸入你的基本資料（例如：男, 21歲, 175, 70, 中等）")
        reply = ReplyMessageRequest(reply_token=event.reply_token, messages=[message])
        messaging_api.reply_message(reply)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

