import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cid_daily_tg as m

SAMPLE = """## 项目列表
### 2026 年 10 月 22 号添加
#### sunerpy - [Github](https://github.com/sunerpy)
* :white_check_mark: [Voltip](https://v.app/)：开源语音输入工具 - [更多介绍](https://v.app/more)

### picaro - [Github](https://github.com/2002pipi)
*  :clock8: [Weird <b>](https://w.app/)：软件 & 工具<br/>第二行

#### Worldku 团队
* :x: [Old](https://o.app/)

### 2026 年 10 月 21 号添加
#### a - [Github](https://github.com/a)
* :white_check_mark: [A](https://a.app/)：简介

### 2026 年 10 月 20 号添加

### 2026 年 10 月 19 号添加
#### b
* :white_check_mark: [B](https://b.app/)：简介
"""


def days():
    return m.parse_days(SAMPLE)


def test_parse_days_and_entries():
    d = days()
    assert [x.date.isoformat() for x in d] == ["2026-10-22", "2026-10-21", "2026-10-20", "2026-10-19"]
    e = d[0].entries
    assert [x.name for x in e] == ["Voltip", "Weird <b>", "Old"]
    assert e[0].author == "sunerpy" and e[0].author_url == "https://github.com/sunerpy"
    assert e[1].author == "picaro" and e[1].status == "clock8"  # ### 格式作者 + 多空白 bullet
    assert e[2].author == "Worldku 团队" and e[2].author_url is None
    assert d[2].entries == []


def test_render_escapes_and_converts():
    e = days()[0].entries[1]
    out = m.render_entry(e)
    assert "Weird &lt;b&gt;" in out and "軟體 &amp; 工具" in out and "<br" not in out
    first = m.render_entry(days()[0].entries[0])
    assert '<a href="https://v.app/more">更多介紹</a>' in first
    assert "開源語音輸入工具" in first


def test_desc_truncates_outside_links():
    long = "字" * 700 + " [x](https://x.app)"
    out = m.render_desc(long)
    assert out.endswith("…") and "<a" not in out and len(out) <= m.DESC_LIMIT + 1


def test_build_messages_split_under_limit():
    day = m.Day(dt.date(2026, 10, 22), [m.Entry("white_check_mark", f"P{i}", f"https://p{i}.app", "介绍" * 200, "u", None)
                                       for i in range(30)])
    msgs = m.build_messages(day)
    assert len(msgs) > 1 and all(len(x) <= 4096 for x in msgs)
    assert "本日新增 30" in msgs[0] and m.SOURCE_REPO in msgs[-1]


def test_pick_pending():
    d = days()
    today = dt.date(2026, 10, 23)
    assert [x.date.day for x in m.pick_pending(d, today, None)] == [22]  # 首次只發最新完整日
    assert [x.date.day for x in m.pick_pending(d, today, "2026-10-19")] == [21, 22]  # 空日(20)略過
    assert m.pick_pending(d, today, "2026-10-22") == []
    assert [x.date.day for x in m.pick_pending(d, dt.date(2026, 10, 22), "2026-10-18")] == [19, 21]  # 當日未結束不發
    assert [x.date.day for x in m.pick_pending(d, today, "2026-10-22", forced=dt.date(2026, 10, 21))] == [21]
    assert [x.date.day for x in m.pick_pending(d, today, None, backfill=2, sent_dates=["2026-10-22"])] == [21]


def test_keepalive_due():
    t = dt.date(2026, 10, 23)
    assert m.keepalive_due({}, t)
    assert not m.keepalive_due({"last_checked": "2026-10-10"}, t)
    assert m.keepalive_due({"last_checked": "2026-09-20"}, t)
