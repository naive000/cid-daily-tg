# cid-daily-tg

把 [1c7/chinese-independent-developer](https://github.com/1c7/chinese-independent-developer) 主版面每天新增的獨立開發者產品，簡轉繁後整理成日報發到 Telegram 頻道 [@just_like_tech_ai](https://t.me/just_like_tech_ai)。

- 流程：GitHub Actions 每天 09:17（台北）抓 README → 找出尚未發送、且已結束的日期（隔天發前一天，避免當天還在增減）→ 只把介紹文字以 OpenCC `s2twp` 轉繁體 → 建 Telegraph 全文頁 → 頻道發索引訊息（標題＋產品清單＋「閱讀全文」按鈕，對標 ruanyf-weekly-tg）→ 成功才寫回 `state.json`。無 LLM。
- 只收主版面（打開即用的產品）；程序員版面、遊戲版面、歷史歸檔不收。全收不篩選。
- 首次啟用只發最新一個完整日，不補歷史；要補用 `--backfill N`。
- 內容署名：每則訊息附來源 repo 連結，並保留投稿者 GitHub 連結。來源 repo 無 LICENSE，內容為投稿者公開的產品介紹。

## Secrets（Settings → Secrets → Actions）

| 名稱 | 說明 |
|---|---|
| `TG_BOT_TOKEN` | bot `@tech_intel_signal_bot` 的 token |
| `TG_CHAT_ID` | 頻道 id（`-100…`；bot 須是管理員且可發佈） |
| `TELEGRAPH_TOKEN` | Telegraph 帳號 token（`--create-telegraph-account` 產生） |

## 本機

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/pytest -q
.venv/bin/python cid_daily_tg.py --dry-run          # 只印訊息，不發送、不寫 state
TG_BOT_TOKEN=… TG_CHAT_ID=… TELEGRAPH_TOKEN=… .venv/bin/python cid_daily_tg.py --date 2026-10-22   # 強制重發某天
```

## 驗證

- Actions 的 `daily` workflow 綠燈，且 `state.json` 的 `last_date` 前進。
- 訊息真的到達聊天室（公開頻道可看 `https://t.me/s/<頻道名>`）。
- 保活：公開 repo 60 天無活動會停用排程；有新內容時每天都會 commit state，無新內容時每 25 天寫一次 `last_checked`。

## 已知限制

- 已發送的日期若事後被補條目，不會重發。
- Telegraph 頁建了刪不掉（只能 editPage），別亂建測試頁；發送失敗重試會重用 `state.json` 的 `pages` 記錄。
- 項目被搬到歷史歸檔或刪除，不會撤回已發訊息。
