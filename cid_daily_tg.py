"""中國獨立開發者項目日報 → Telegram。

來源：1c7/chinese-independent-developer 主版面 README.md，每天一個「### YYYY 年 M 月 D 号添加」區塊。
流程：抓 README → 找出尚未發送的「已結束日」（台北時間今天之前）→ 只把介紹文字簡轉繁（OpenCC s2twp）
→ 合成 1～N 則 Telegram 訊息 → 全部成功才寫回 state.json。無 LLM。
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from opencc import OpenCC

SOURCE_REPO = "1c7/chinese-independent-developer"
SOURCE_URL = f"https://github.com/{SOURCE_REPO}"
README_URL = f"https://raw.githubusercontent.com/{SOURCE_REPO}/master/README.md"
STATE_PATH = Path(__file__).with_name("state.json")
TAIPEI = dt.timezone(dt.timedelta(hours=8))

MSG_LIMIT = 3800  # Telegram 單則 4096，留餘裕給 HTML 標籤
DESC_LIMIT = 600  # 單一項目介紹上限，超過截斷
SEND_INTERVAL = 3.0  # 秒；同一聊天約 20 則／分鐘上限
KEEPALIVE_DAYS = 25  # 公開 repo 60 天無活動會停排程
MAX_DAYS_PER_RUN = 7
SENT_DATES_KEEP = 60

STATUS_ICON = {"white_check_mark": "✅", "clock8": "🕗", "x": "❌"}

_cc = OpenCC("s2twp")


def to_tw(text: str) -> str:
    return _cc.convert(text)


# ---------- HTTP ----------

def _request(url: str, *, data: bytes | None = None, headers: dict | None = None, label: str) -> bytes:
    """所有對外請求的唯一出口。錯誤訊息只帶 label，避免 token 隨 URL 進公開 log。"""
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            body = json.loads(e.read())
            detail = f" ({body.get('description') or body.get('error') or body.get('message')})"
        except Exception:
            pass
        raise RuntimeError(f"{label}: HTTP {e.code}{detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{label}: {e.reason}") from None


def with_flood_retry(fn, attempts: int = 4):
    """碰到 Telegram 'retry after n' 就等待後重試。"""
    for i in range(attempts):
        try:
            return fn()
        except RuntimeError as e:
            m = re.search(r"retry after (\d+)", str(e))
            if not m or i == attempts - 1:
                raise
            wait = int(m.group(1)) + 1
            print(f"rate limited, sleep {wait}s")
            time.sleep(wait)


def fetch_readme() -> str:
    return _request(README_URL, label="fetch README").decode("utf-8")


# ---------- Parse ----------

DAY_RE = re.compile(r"(?m)^### (\d{4}) 年 (\d{1,2}) 月 (\d{1,2}) 号添加\s*$")
AUTHOR_RE = re.compile(r"^#{3,4}\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\*\s+:(\w+):\s*\[(.+?)\]\((\S+?)\)\s*(?:[：:]\s*(.*))?$")
GITHUB_LINK_RE = re.compile(r"\[Github\]\((\S+?)\)", re.I)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((\S+?)\)")


@dataclass
class Entry:
    status: str
    name: str
    url: str
    desc: str
    author: str
    author_url: str | None


@dataclass
class Day:
    date: dt.date
    entries: list[Entry] = field(default_factory=list)


def parse_author(line: str) -> tuple[str, str | None]:
    """`#### 名稱(城市) - [Github](url), [博客](url)` → (名稱, github url)。"""
    m = AUTHOR_RE.match(line)
    text = m.group(1) if m else line
    gh = GITHUB_LINK_RE.search(text)
    name = re.split(r"\s+-\s+\[", text, maxsplit=1)[0].strip()
    return name, gh.group(1) if gh else None


def parse_days(markdown: str) -> list[Day]:
    parts = DAY_RE.split(markdown)
    days: list[Day] = []
    for i in range(1, len(parts) - 3, 4):
        try:
            date = dt.date(int(parts[i]), int(parts[i + 1]), int(parts[i + 2]))
        except ValueError:
            continue
        day = Day(date)
        author, author_url = "", None
        for line in parts[i + 3].split("\n"):
            line = line.rstrip()
            if re.match(r"^#{3,4}\s", line):
                author, author_url = parse_author(line)
                continue
            m = BULLET_RE.match(line)
            if m:
                day.entries.append(Entry(m.group(1), m.group(2).strip(), m.group(3), (m.group(4) or "").strip(),
                                         author, author_url))
        days.append(day)
    return days


# ---------- Render ----------

def render_desc(desc: str) -> str:
    """介紹文字 → HTML：文字簡轉繁並跳脫，markdown 連結保留成錨點；超長在連結邊界外截斷。"""
    desc = re.sub(r"<br\s*/?>", " ", desc)
    desc = re.sub(r"[*`]", "", desc)
    out, used, pos = [], 0, 0

    def add(text: str) -> bool:
        nonlocal used
        text = to_tw(re.sub(r"\s+", " ", text))
        room = DESC_LIMIT - used
        if len(text) > room:
            out.append(html.escape(text[:room].rstrip()) + "…")
            return False
        out.append(html.escape(text))
        used += len(text)
        return True

    for m in MD_LINK_RE.finditer(desc):
        if not add(desc[pos:m.start()]):
            return "".join(out).strip()
        label = to_tw(m.group(1))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(label)}</a>')
        used += len(label)
        pos = m.end()
    add(desc[pos:])
    return "".join(out).strip()


def render_entry(e: Entry) -> str:
    icon = STATUS_ICON.get(e.status, "•")
    head = f'{icon} <a href="{html.escape(e.url, quote=True)}">{html.escape(e.name)}</a>'
    if e.author:
        who = html.escape(e.author)
        if e.author_url:
            who = f'<a href="{html.escape(e.author_url, quote=True)}">{who}</a>'
        head += f" · {who}"
    desc = render_desc(e.desc)
    return head + (f"\n{desc}" if desc else "")


def build_messages(day: Day) -> list[str]:
    header = f"<b>🧑‍💻 中國獨立開發者 · {day.date.isoformat()}</b>\n本日新增 {len(day.entries)} 個項目"
    footer = f'來源：<a href="{SOURCE_URL}">{SOURCE_REPO}</a>'
    blocks = [render_entry(e) for e in day.entries]
    messages: list[str] = []
    cur = header
    for b in blocks:
        if len(cur) + len(b) + 2 > MSG_LIMIT:
            messages.append(cur)
            cur = ""
        cur = f"{cur}\n\n{b}" if cur else b
    if len(cur) + len(footer) + 2 > MSG_LIMIT:
        messages.append(cur)
        cur = footer
    else:
        cur = f"{cur}\n\n{footer}"
    messages.append(cur)
    return messages


# ---------- Telegram ----------

def telegram_send(bot_token: str, chat_id: str, text: str) -> None:
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"is_disabled": True}),
    }
    raw = _request(f"https://api.telegram.org/bot{bot_token}/sendMessage", data=urllib.parse.urlencode(params).encode(),
                   headers={"Content-Type": "application/x-www-form-urlencoded"}, label="telegram sendMessage")
    if not json.loads(raw).get("ok"):
        raise RuntimeError("telegram sendMessage: not ok")


# ---------- State ----------

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_date": None, "sent_dates": [], "last_checked": None, "last_sent": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick_pending(days: list[Day], today: dt.date, last_date: str | None, forced: dt.date | None = None,
                 backfill: int = 0, sent_dates: list[str] | None = None) -> list[Day]:
    """回傳要發送的日子，由舊到新。只含「已結束日」（早於今天），空日不算。"""
    done = sorted((d for d in days if d.date < today and d.entries), key=lambda d: d.date)
    if forced:
        return [d for d in done if d.date == forced]
    if backfill:
        sent = set(sent_dates or [])
        return [d for d in done[-backfill:] if d.date.isoformat() not in sent]
    if not last_date:  # 首次啟用：只發最新一個完整日，不補歷史
        return done[-1:]
    last = dt.date.fromisoformat(last_date)
    return [d for d in done if d.date > last][:MAX_DAYS_PER_RUN]


def keepalive_due(state: dict, today: dt.date) -> bool:
    last = state.get("last_checked")
    return not last or (today - dt.date.fromisoformat(last)).days >= KEEPALIVE_DAYS


def _require_env(*names: str) -> dict:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")
    return {n: os.environ[n] for n in names}


def send_day(day: Day, env: dict, dry_run: bool) -> None:
    msgs = build_messages(day)
    for i, text in enumerate(msgs):
        if dry_run:
            print(f"--- {day.date} [{i + 1}/{len(msgs)}] ({len(text)} chars) ---\n{text}\n")
            continue
        with_flood_retry(lambda t=text: telegram_send(env["TG_BOT_TOKEN"], env["TG_CHAT_ID"], t))
        time.sleep(SEND_INTERVAL)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="強制重發指定日期 YYYY-MM-DD")
    ap.add_argument("--backfill", type=int, default=0, help="補發最近 N 個已結束日（跳過已發）")
    ap.add_argument("--dry-run", action="store_true", help="只印訊息，不發送、不寫 state")
    args = ap.parse_args(argv)

    today = dt.datetime.now(TAIPEI).date()
    state = load_state()
    days = parse_days(fetch_readme())
    forced = dt.date.fromisoformat(args.date) if args.date else None
    pending = pick_pending(days, today, state.get("last_date"), forced, args.backfill, state.get("sent_dates"))
    print(f"today={today} last_date={state.get('last_date')} pending={[d.date.isoformat() for d in pending]}")

    env = {} if args.dry_run else _require_env("TG_BOT_TOKEN", "TG_CHAT_ID")
    try:
        for day in pending:
            send_day(day, env, args.dry_run)
            if args.dry_run:
                continue
            state["sent_dates"] = sorted(set(state.get("sent_dates", [])) | {day.date.isoformat()})[-SENT_DATES_KEEP:]
            if not forced and (not state.get("last_date") or day.date.isoformat() > state["last_date"]):
                state["last_date"] = day.date.isoformat()
            state["last_sent"] = today.isoformat()
            state["last_checked"] = today.isoformat()
            save_state(state)  # 每完成一天就寫回，中途失敗不會重發已完成的日子
    finally:
        if not args.dry_run and not pending and keepalive_due(state, today):
            state["last_checked"] = today.isoformat()
            save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
