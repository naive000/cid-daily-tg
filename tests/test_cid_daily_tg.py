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


def test_desc_segments_convert_and_keep_links():
    e = days()[0].entries[0]
    segs = m.desc_segments(e.desc)
    assert ("開源語音輸入工具 - ", None) in segs and ("更多介紹", "https://v.app/more") in segs
    odd = m.desc_segments(days()[0].entries[1].desc)
    assert "".join(t for t, _ in odd) == "軟體 & 工具 第二行"  # <br/> 去掉、簡轉繁


def test_desc_truncates_outside_links():
    segs = m.desc_segments("字" * 700 + " [x](https://x.app)")
    assert segs[-1][0].endswith("…") and all(u is None for _, u in segs)
    assert sum(len(t) for t, _ in segs) <= m.DESC_LIMIT + 1


def test_index_text_escapes_and_lists():
    day = days()[0]
    text = m.build_index_text(day)
    assert text.startswith("<b>🧑‍💻 中國獨立開發者日報 · 2026-10-22</b>") and "本日新增 3 個項目" in text
    assert "・Voltip — 開源語音輸入工具" in text and "Weird &lt;b&gt;" in text
    assert len(text) < 4096


def test_index_caps_items():
    day = m.Day(dt.date(2026, 10, 22), [m.Entry("white_check_mark", f"P{i}", f"https://p{i}.app", "介绍", "u", None)
                                       for i in range(60)])
    text = m.build_index_text(day)
    assert text.count("・P") == m.INDEX_MAX_ITEMS and "另 20 個見全文" in text and len(text) < 4096


def test_page_nodes_and_size_guard():
    import json
    day = days()[0]
    nodes = json.loads(m.serialize_page(day))
    h4 = [n for n in nodes if n["tag"] == "h4"]
    assert len(h4) == 3 and h4[0]["children"][1] == {"tag": "a", "attrs": {"href": "https://v.app/"}, "children": ["Voltip"]}
    big = m.Day(dt.date(2026, 10, 22), [m.Entry("white_check_mark", f"P{i}", f"https://p{i}.app", "介绍" * 300, "u", None)
                                       for i in range(120)])
    assert len(m.serialize_page(big).encode()) <= m.PAGE_LIMIT


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
