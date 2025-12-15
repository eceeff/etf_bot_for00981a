import requests
import pandas as pd
import os
import json
import html
from bs4 import BeautifulSoup
from datetime import datetime

# --- 設定區 ---
TARGET_URL = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"
TELEGRAM_TOKEN = os.environ.get("TG_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
DATA_FILE = "00981a_holdings.csv"


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")


def get_current_holdings():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
    }
    try:
        response = requests.get(TARGET_URL, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        data_div = soup.find('div', id='DataAsset')

        if not data_div:
            return None, None

        # 解析 JSON
        raw_json_str = data_div.get('data-content', '')
        json_str = html.unescape(raw_json_str)
        assets_data = json.loads(json_str)

        stock_data = []
        cash_position = 0.0
        nav_value = 0.0

        for item in assets_data:
            if item.get('AssetCode') == 'NAV':
                nav_value = float(item.get('Value', 0))

            if item.get('AssetCode') == 'CASH':
                cash_value = float(item.get('Value', 0))
                if nav_value > 0:
                    cash_position = (cash_value / nav_value) * 100

            if item.get('AssetCode') == 'ST':
                details = item.get('Details', [])
                for stock in details:
                    stock_data.append({
                        'code': stock.get('DetailCode'),
                        'name': stock.get('DetailName'),
                        'weight': float(stock.get('NavRate', 0)),
                        'shares': int(float(stock.get('Share', 0)))  # 新增：擷取股數
                    })

        df = pd.DataFrame(stock_data)
        return df, cash_position

    except Exception as e:
        print(f"爬取或解析失敗: {e}")
        send_telegram_message(f"⚠️ 00981A 爬蟲解析錯誤: {str(e)}")
        return None, None


def compare_and_report():
    print("正在抓取今日數據...")
    new_df, current_cash = get_current_holdings()

    if new_df is None or new_df.empty:
        print("無數據")
        return

    # 讀取昨天的數據
    if os.path.exists(DATA_FILE):
        old_df = pd.read_csv(DATA_FILE)
        # 兼容性檢查：如果舊檔案沒有 shares 欄位，視為重新初始化
        if 'shares' not in old_df.columns:
            old_df = pd.DataFrame(columns=['name', 'code', 'weight', 'shares'])
            send_telegram_message("🔄 偵測到舊版數據格式，已重置基準以支援股數追蹤。")
    else:
        old_df = pd.DataFrame(columns=['name', 'code', 'weight', 'shares'])
        send_telegram_message("🚀 00981A 監控機器人(V3) 初始化完成！")

    # --- 資料預處理 ---
    # 統一轉為字串
    old_df['code'] = old_df['code'].astype(str)
    new_df['code'] = new_df['code'].astype(str)

    # 建立查找字典 {code: shares} 和 {code: weight}
    old_shares_map = dict(zip(old_df['code'], old_df['shares']))
    new_shares_map = dict(zip(new_df['code'], new_df['shares']))

    old_weight_map = dict(zip(old_df['code'], old_df['weight']))
    new_weight_map = dict(zip(new_df['code'], new_df['weight']))

    name_map = dict(zip(new_df['code'], new_df['name']))
    name_map.update(dict(zip(old_df['code'], old_df['name'])))

    added = set(new_shares_map.keys()) - set(old_shares_map.keys())
    removed = set(old_shares_map.keys()) - set(new_shares_map.keys())

    report_lines = []

    # 標題
    title = f"📊 **00981A 持股日報** ({datetime.now().strftime('%m/%d')})"
    if current_cash:
        title += f"\n💰 現金水位: `{current_cash:.2f}%`"
    report_lines.append(title)

    has_change = False

    # 1. 新增持股
    if added:
        has_change = True
        report_lines.append("\n🟢 **新進駐標的：**")
        for code in added:
            shares = new_shares_map[code]
            w = new_weight_map[code]
            # 格式：台積電 (2330): 2,722 張 (9.07%)
            report_lines.append(f"• {name_map.get(code)} ({code}): `{shares:,}` 股 ({w}%)")

    # 2. 剔除持股
    if removed:
        has_change = True
        report_lines.append("\n🔴 **已清倉退出：**")
        for code in removed:
            old_shares = old_shares_map[code]
            report_lines.append(f"• {name_map.get(code)} ({code}): 拋售 `{old_shares:,}` 股")

    # 3. 股數變動 (真正的加減碼)
    # 找出同時存在於兩邊的股票
    common_codes = set(new_shares_map.keys()) & set(old_shares_map.keys())

    share_changes = []
    for code in common_codes:
        diff = new_shares_map[code] - old_shares_map[code]

        # 過濾雜訊：這裡設定只要股數有變動就回報 (您可設 diff != 0 或 abs(diff) > 1000)
        if diff != 0:
            has_change = True
            icon = "🔺" if diff > 0 else "🔻"
            w_diff = new_weight_map[code] - old_weight_map[code]

            # 格式：🔺 台積電: +50,000 股 (權重 +0.1%)
            msg = f"{icon} {name_map.get(code)}: `{diff:+,}` 股"

            # 若權重變動明顯也一併顯示，方便參考
            if abs(w_diff) >= 0.01:
                msg += f" (權重 {w_diff:+.2f}%)"

            share_changes.append((diff, msg))  # 存起來以便排序

    # 依變動股數絕對值排序 (大動作排前面)
    share_changes.sort(key=lambda x: abs(x[0]), reverse=True)

    if share_changes:
        report_lines.append("\n⚖️ **持倉調整 (股數變化)：**")
        for _, msg in share_changes:
            report_lines.append(msg)

    # 發送通知
    if has_change:
        final_msg = "\n".join(report_lines)
        print(final_msg)
        send_telegram_message(final_msg)
    else:
        print("今日股數無變化 (可能是休市或無交易)")

    # 存檔
    new_df.to_csv(DATA_FILE, index=False)


if __name__ == "__main__":
    compare_and_report()