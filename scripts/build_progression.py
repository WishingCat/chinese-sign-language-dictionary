"""Generate 主题难度进阶.md from sign_themed.db.

The ordering comes from the `themes` table (populated by
`add_theme_order.py`); words come from `signs` + `meanings`. Words are
listed in dictionary order (letter, then sign id, then meaning order);
signs with multiple打法 get ①②… suffixes.
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "sign_themed.db")
OUT = os.path.join(ROOT, "主题难度进阶.md")


def load_theme_order() -> list[tuple[str, str]]:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT name, tier FROM themes ORDER BY difficulty_rank"
    ).fetchall()
    con.close()
    return rows


def load_theme_words():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT s.id, s.theme, s.letter, m.text, m.variant_index, m.order_in_entry
        FROM signs s JOIN meanings m ON m.sign_id = s.id
        WHERE s.theme IS NOT NULL
        ORDER BY s.letter, s.id, m.order_in_entry
        """
    ).fetchall()
    con.close()

    by_theme: dict[str, list[tuple]] = {}
    for sid, theme_raw, letter, text, vidx, order in rows:
        # Multi-theme signs use '|' separator; list the word under each.
        for theme in theme_raw.split("|"):
            by_theme.setdefault(theme, []).append((letter, sid, order, text, vidx))
    # Deduplicate while keeping order (same word can show up via multi-meaning).
    for t, items in by_theme.items():
        seen = set()
        dedup = []
        for it in items:
            key = (it[1], it[3], it[4])  # sign_id + text + variant
            if key in seen:
                continue
            seen.add(key)
            dedup.append(it)
        by_theme[t] = dedup
    return by_theme


def format_word(text: str, variant_index):
    if variant_index:
        circled = "①②③④⑤⑥⑦⑧⑨"[variant_index - 1] if 1 <= variant_index <= 9 else f"({variant_index})"
        return f"{text}{circled}"
    return text


def main():
    theme_order = load_theme_order()
    by_theme = load_theme_words()

    lines: list[str] = []
    lines.append("# 主题难度进阶")
    lines.append("")
    lines.append(
        "主题难度顺序来自 `sign_themed.db` 的 `themes` 表（字段 "
        "`difficulty_rank` / `tier`）。同一主题下的词语按首字母、词条 id、"
        "释义顺序排列；同一手语有多种打法时词尾带圆圈序号①②…。"
    )
    lines.append("")
    lines.append(
        "> 若同一手语同时属于多个主题（`signs.theme` 以 `|` 分隔），"
        "该词在每个所属主题下均会出现一次。"
    )
    lines.append("")

    total_words = 0
    prev_tier = None
    for idx, (theme, tier) in enumerate(theme_order, 1):
        items = by_theme.get(theme, [])
        total_words += len(items)
        if tier != prev_tier:
            lines.append(f"### 〔{tier}〕")
            lines.append("")
            prev_tier = tier
        lines.append(f"## {idx}. 【{theme}】（{len(items)} 词）")
        lines.append("")
        if not items:
            lines.append("_（暂无数据库匹配词）_")
            lines.append("")
            continue
        # Render as space-joined list, wrapping roughly every 10 words.
        words = [format_word(t, v) for _, _, _, t, v in items]
        for i in range(0, len(words), 10):
            lines.append("、".join(words[i:i + 10]))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**总计**：{len(theme_order)} 个主题，{total_words} 条词语条目。")
    lines.append("")
    lines.append("## 难度排序依据")
    lines.append("")
    lines.append(
        "- **入门（1–5）**：常用语、数字、亲属、身体、颜色——均为高频、指代具体、"
        "打法以指向自身/身体部位为主，无需抽象化。"
    )
    lines.append(
        "- **初级（6–12）**：日常名词场景——时间、生活、食物、蔬果、动物、植物、衣物，"
        "多数词可以用象形打法直接呈现。"
    )
    lines.append(
        "- **中初（13–17）**：家具、自然、交通、身体运动、体育。词汇量变大、"
        "复合/组合手势增多，但含义依然具体。"
    )
    lines.append(
        "- **中级（18–20）**：形容词、社交、情绪性格。脱离具体指代，"
        "进入状态/情感/互动层面，需要更多面部表情与方向变化。"
    )
    lines.append(
        "- **中高（21–25）**：身体症状、就医、学习、文化、职业。领域专有词增多，"
        "需要生活经验支撑。"
    )
    lines.append(
        "- **高级（26–29）**：经济、科目专业、政治、虚词。抽象/术语/语法功能词，"
        "虚词在手语里多用词序、眉眼与方向表达，是典型难点。"
    )
    lines.append(
        "- **专项（30–31）**：其他常见词（跨主题抽象短语）、爱心社（组织专名），"
        "主要用于实战拓展。"
    )
    lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {OUT}  ({total_words} word entries across {len(theme_order)} themes)")


if __name__ == "__main__":
    main()
