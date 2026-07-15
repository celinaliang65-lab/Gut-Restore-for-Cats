# AnimalBiome 價格監控機器人

每天自動抓取指定商品（預設：Gut Restore for Cats）的價格，
若出現「劃線促銷價」或「比上次記錄更便宜」，就發 LINE 推播通知你。

## 運作方式

1. GitHub Actions 每天台灣時間 09:00 自動執行 `price_monitor.py`
2. 程式抓取商品的 Shopify JSON（網址加 `.json`），取得各規格的現價與劃線價
3. 跟 `data/price_state.json` 裡記錄的上次價格比對
4. 有降價 / 促銷 → 組成 LINE Flex Message 卡片推播；沒有變化 → 不通知
5. 執行完後把最新價格寫回 `data/price_state.json` 並 commit

## 部署步驟

1. 建立一個新的 GitHub repo，把這個資料夾內容全部上傳
2. 到 repo 的 **Settings → Secrets and variables → Actions** 新增：
   - `LINE_CHANNEL_ACCESS_TOKEN`：你的 LINE Bot channel access token
   - `LINE_USER_ID_1`（及需要的話 `LINE_USER_ID_2` 等）：要接收通知的 LINE 使用者 ID
3. 完成後排程就會自動運作。也可以到 **Actions** 頁籤手動點 **Run workflow** 立刻測試一次

## 新增/修改追蹤商品

打開 `price_monitor.py`，找到最上方的「可調整參數區」，
在 `PRODUCTS` 這個 list 裡新增項目即可，例如：

```python
PRODUCTS = [
    {
        "name": "Gut Restore for Cats",
        "url": "https://www.animalbiome.com/products/kittybiome-gut-restore-supplement",
        "variants": ["30 Capsules", "60 Capsules"],
    },
    {
        "name": "Gut Maintain for Cats",
        "url": "https://www.animalbiome.com/products/新商品網址",
        "variants": [],  # 空 list = 追蹤該商品全部規格
    },
]
```

## 注意事項

- 這個程式抓的是「官網當下顯示的價格」，抓不到像你之前收到的
  Email 購物車折扣碼（PA15-xxx、PA20-xxx 那種），因為那類代碼是
  Klaviyo/Mailchimp 等 EDM 系統依「個人購物車行為」動態產生的，
  沒有對外公開的 API 可以查詢。這套系統只能監控「網站上公開顯示」
  的價格與促銷。
- 第一次執行時，因為 `data/price_state.json` 是空的，所以不會馬上
  發通知（沒有「之前的價格」可以比較），從第二次執行開始才會真正
  發揮比價功能。
