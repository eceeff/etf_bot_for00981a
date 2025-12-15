import requests

# 請填入您的資訊
TOKEN = "8561176671:AAFdZRHJ1PG7cYzE8g1LRAiKn6YZOjkwkG0"
CHAT_ID = "977857400"

def test_telegram():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "🎉 測試成功！機器人已連線。",
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ 訊息發送成功！請檢查您的 Telegram。")
        else:
            print(f"❌ 發送失敗，錯誤代碼: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ 連線錯誤: {e}")

if __name__ == "__main__":
    test_telegram()
