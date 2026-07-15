# -*- coding: utf-8 -*-
"""
AnimalBiome 商品降價 / 促銷監控程式
每次執行會：
1. 抓取下方 PRODUCTS 清單中每個商品的 Shopify JSON 資料
2. 比對「現價」「劃線原價 compare_at_price」與上次記錄的價格
3. 若價格下降、或出現劃線促銷價，且與上次通知不同 → 發送 LINE 推播
4. 更新 data/price_state.json 記錄最新價格，供下次比對使用
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

# ╔═══════════════════════════════════════════════════════╗
# ║                    可調整參數區                          ║
# ╠═══════════════════════════════════════════════════════╣
# ║ PRODUCTS: 要追蹤的商品清單                                ║
# ║   name       - 顯示在 LINE 卡片上的商品名稱                ║
# ║   url        - 商品頁網址（不含 .json，程式會自動加上）      ║
# ║   variants   - 要追蹤的規格關鍵字（對應 Shopify variant     ║
# ║                title，例如 "30 Capsules"）。留空 [] 代表    ║
# ║                追蹤該商品全部規格。                         ║
# ║                                                         ║
# ║ 新增/移除追蹤商品：直接增減下面 list 裡的項目即可              ║
# ╚═══════════════════════════════════════════════════════╝
PRODUCTS = [
    {
        "name": "Gut Restore for Cats",
        "url": "https://www.animalbiome.com/products/kittybiome-gut-restore-supplement",
        "variants": ["30 Capsules", "60 Capsules"],
    },
]

# 卡片顏色（沿用低飽和暖色系慣例，可自行調整）
COLOR_HEADER_BG = "#4E5D4E"      # 深綠（呼應 AnimalBiome 品牌色）
COLOR_HEADER_TEXT = "#FFFFFF"
COLOR_BODY_BG = "#F5F3EE"
COLOR_PRICE_DOWN = "#B5433D"     # 降價強調色（暗紅）
COLOR_PRICE_NORMAL = "#3A3A3A"

STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "price_state.json")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_IDS = [
    v for k, v in os.environ.items()
    if k.startswith("LINE_USER_ID_") and v
]

TAIWAN_TZ = timezone(timedelta(hours=8))


def taiwan_now():
    return datetime.now(TAIWAN_TZ)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_product_json(product_url):
    """抓取 Shopify 商品頁 JSON 資料，失敗時回傳 None（不中斷整體流程）"""
    json_url = product_url.rstrip("/") + ".json"
    try:
        resp = requests.get(json_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (price-monitor-bot)"
        })
        resp.raise_for_status()
        return resp.json().get("product")
    except (requests.RequestException, ValueError) as e:
        print(f"[警告] 抓取失敗 {json_url}: {e}")
        return None


def extract_variant_prices(product_json, wanted_variants):
    """
    從 Shopify product JSON 取出目標規格的價格資訊
    回傳格式: [{"variant": "30 Capsules", "price": 105.0, "compare_at_price": 130.0 or None}, ...]
    """
    if not product_json:
        return []

    results = []
    for v in product_json.get("variants", []):
        title = v.get("title", "")
        if wanted_variants and title not in wanted_variants:
            continue
        try:
            price = float(v.get("price"))
        except (TypeError, ValueError):
            continue
        compare_raw = v.get("compare_at_price")
        compare_at = None
        if compare_raw:
            try:
                compare_val = float(compare_raw)
                # compare_at_price 必須「高於」現價才算是真的促銷標示
                if compare_val > price:
                    compare_at = compare_val
            except (TypeError, ValueError):
                pass
        results.append({
            "variant": title,
            "price": price,
            "compare_at_price": compare_at,
        })
    return results


def build_daily_status_message(checked_items):
    """
    無價格變動時發送的「每日巡查回報」卡片
    checked_items: [{"product": name, "variant": ..., "price": ..., "url": ...}, ...]
    """
    body_rows = []
    for item in checked_items:
        body_rows.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"🐱 {item['variant']}",
                    "size": "sm",
                    "color": "#3A3A3A",
                    "flex": 3,
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": f"${item['price']:.2f}",
                    "size": "sm",
                    "weight": "bold",
                    "color": COLOR_HEADER_BG,
                    "align": "end",
                    "flex": 2,
                },
            ],
        })

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": COLOR_HEADER_BG,
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "🐱💊 每日價格巡查",
                    "color": COLOR_HEADER_TEXT,
                    "weight": "bold",
                    "size": "sm",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": COLOR_BODY_BG,
            "spacing": "sm",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": checked_items[0]["product"],
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": f"📅 {taiwan_now().strftime('%Y/%m/%d %H:%M')} 巡查完成",
                    "size": "xs",
                    "color": "#999999",
                    "margin": "sm",
                },
                {
                    "type": "separator",
                    "margin": "md",
                },
                *body_rows,
                {
                    "type": "text",
                    "text": "✅ 今日無降價 / 促銷,價格維持不變",
                    "size": "xs",
                    "color": "#666666",
                    "margin": "lg",
                    "wrap": True,
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": COLOR_HEADER_BG,
                    "action": {
                        "type": "uri",
                        "label": "🔗 前往商品頁面",
                        "uri": checked_items[0]["url"],
                    },
                }
            ],
        },
    }

    return {
        "type": "flex",
        "altText": f"每日價格巡查：{checked_items[0]['product']} 目前無變動",
        "contents": bubble,
    }


def build_line_flex_message(alerts):
    """
    alerts: [{"product": name, "variant": ..., "price": ..., "old_price": ..., "compare_at_price": ...}, ...]
    """
    bubbles = []
    for a in alerts:
        price_line_contents = [
            {
                "type": "text",
                "text": f"NT${a['price']:.2f}".replace("NT$", "$"),
                "size": "xl",
                "weight": "bold",
                "color": COLOR_PRICE_DOWN,
                "flex": 0,
            }
        ]
        if a.get("compare_at_price"):
            price_line_contents.append({
                "type": "text",
                "text": f"  原價 ${a['compare_at_price']:.2f}",
                "size": "sm",
                "color": "#999999",
                "decoration": "line-through",
                "gravity": "bottom",
            })
        elif a.get("old_price") is not None:
            price_line_contents.append({
                "type": "text",
                "text": f"  之前 ${a['old_price']:.2f}",
                "size": "sm",
                "color": "#999999",
                "decoration": "line-through",
                "gravity": "bottom",
            })

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": COLOR_HEADER_BG,
                "paddingAll": "12px",
                "contents": [
                    {
                        "type": "text",
                        "text": "💰 價格變動通知",
                        "color": COLOR_HEADER_TEXT,
                        "weight": "bold",
                        "size": "sm",
                    }
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": COLOR_BODY_BG,
                "spacing": "sm",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": a["product"],
                        "weight": "bold",
                        "size": "md",
                        "wrap": True,
                    },
                    {
                        "type": "text",
                        "text": a["variant"],
                        "size": "sm",
                        "color": "#666666",
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "margin": "md",
                        "contents": price_line_contents,
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLOR_HEADER_BG,
                        "action": {
                            "type": "uri",
                            "label": "前往查看",
                            "uri": a["url"],
                        },
                    }
                ],
            },
        }
        bubbles.append(bubble)

    return {
        "type": "flex",
        "altText": f"價格變動通知：{alerts[0]['product']} 等 {len(alerts)} 項",
        "contents": {
            "type": "carousel",
            "contents": bubbles[:10],  # LINE carousel 上限 10 張
        },
    }


def send_line_push(message):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_IDS:
        print("[警告] 缺少 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID，略過推播")
        return
    for user_id in LINE_USER_IDS:
        try:
            resp = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"to": user_id, "messages": [message]},
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[警告] LINE 推播失敗 ({user_id}): {resp.status_code} {resp.text}")
        except requests.RequestException as e:
            print(f"[警告] LINE 推播例外 ({user_id}): {e}")


def main():
    state = load_state()
    alerts = []
    checked_items = []  # 這次巡查的所有商品現況（不論有無變動都記錄，用於每日回報卡片）

    for product in PRODUCTS:
        product_json = fetch_product_json(product["url"])
        variants = extract_variant_prices(product_json, product["variants"])

        for v in variants:
            key = f"{product['name']}::{v['variant']}"
            prev = state.get(key)
            prev_price = prev.get("price") if prev else None

            is_on_sale = v["compare_at_price"] is not None
            is_price_drop = (
                prev_price is not None and v["price"] < prev_price
            )

            # 只有「第一次偵測到促銷/降價」才通知，避免重複洗版
            already_notified = prev and prev.get("last_alert_price") == v["price"]

            checked_items.append({
                "product": product["name"],
                "variant": v["variant"],
                "price": v["price"],
                "url": product["url"],
            })

            if (is_on_sale or is_price_drop) and not already_notified:
                alerts.append({
                    "product": product["name"],
                    "variant": v["variant"],
                    "price": v["price"],
                    "old_price": prev_price,
                    "compare_at_price": v["compare_at_price"],
                    "url": product["url"],
                })
                state[key] = {
                    "price": v["price"],
                    "last_alert_price": v["price"],
                    "checked_at": taiwan_now().isoformat(),
                }
            else:
                state[key] = {
                    "price": v["price"],
                    "last_alert_price": (prev or {}).get("last_alert_price"),
                    "checked_at": taiwan_now().isoformat(),
                }

    save_state(state)

    if alerts:
        print(f"[通知] 偵測到 {len(alerts)} 項價格變動，發送 LINE 推播")
        message = build_line_flex_message(alerts)
        send_line_push(message)
    elif checked_items:
        print("[完成] 無價格變動，發送每日巡查回報卡片")
        message = build_daily_status_message(checked_items)
        send_line_push(message)
    else:
        print("[警告] 沒有任何商品資料可回報（可能抓取全部失敗）")


if __name__ == "__main__":
    sys.exit(main() or 0)
