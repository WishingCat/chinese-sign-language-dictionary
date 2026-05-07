"""Insert a `themes` table into sign_themed.db with difficulty ranking.

Schema:
    themes(name TEXT PRIMARY KEY,
           difficulty_rank INTEGER UNIQUE NOT NULL,
           tier TEXT NOT NULL)

This is the single source of truth for the pedagogical ordering used by
both 主题难度进阶.md and the consuming signo-web app.
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "sign_themed.db")

# (tier, [themes in ascending difficulty])
TIERS: list[tuple[str, list[str]]] = [
    ("入门", ["常用语", "数字", "亲属", "身体", "颜色"]),
    ("初级", ["时间", "生活", "食物", "蔬果", "动物", "植物", "衣物"]),
    ("中初", ["家具", "自然", "交通", "身体运动", "体育"]),
    ("中级", ["形容词", "社交", "情绪性格"]),
    ("中高", ["身体症状", "就医", "学习", "文化", "职业"]),
    ("高级", ["经济", "科目专业", "政治", "虚词"]),
    ("专项", ["其他常见词", "爱心社"]),
]


def main():
    rows = []
    rank = 1
    for tier, names in TIERS:
        for n in names:
            rows.append((n, rank, tier))
            rank += 1

    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS themes")
    cur.execute(
        """
        CREATE TABLE themes (
            name TEXT PRIMARY KEY,
            difficulty_rank INTEGER UNIQUE NOT NULL,
            tier TEXT NOT NULL
        )
        """
    )
    cur.executemany(
        "INSERT INTO themes(name, difficulty_rank, tier) VALUES (?, ?, ?)",
        rows,
    )

    # Sanity: every theme referenced on signs.theme must exist in this table.
    referenced = set()
    for (raw,) in cur.execute(
        "SELECT DISTINCT theme FROM signs WHERE theme IS NOT NULL"
    ):
        for t in raw.split("|"):
            referenced.add(t)
    defined = {r[0] for r in rows}
    missing = referenced - defined
    if missing:
        raise SystemExit(f"signs.theme references unknown themes: {missing}")

    con.commit()
    con.close()
    print(f"inserted {len(rows)} themes into themes table")
    print(f"covers all {len(referenced)} themes referenced by signs.theme")


if __name__ == "__main__":
    main()
