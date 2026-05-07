"""
Add a `theme` tag to every sign whose Chinese meaning appears in
`手语词库主题分类（2025.2）.docx`.

Pipeline:
  1. Unzip the docx and read document.xml paragraphs.
  2. Walk paragraphs: lines matching `【xxx】` start a new theme; the following
     word-list paragraphs accumulate into that theme until the next `【...】`.
  3. Split each word list into atomic Chinese tokens (respecting `、`, `/`,
     parenthetical synonyms, and stripping `*` / circled-digit variant marks).
  4. Copy signs.db -> sign_themed.db, add `theme TEXT` to `signs`, then for
     each token UPDATE signs.theme via meanings.text exact match.

Notes: words not found verbatim in the DB are left untagged (per spec).
No semantic fallback is applied.
"""
import os, re, shutil, sqlite3, sys, tempfile, zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCX = os.path.join(ROOT, "手语词库主题分类（2025.2）.docx")
SRC_DB = os.path.join(ROOT, "signs.db")
DST_DB = os.path.join(ROOT, "sign_themed.db")
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

THEME_RE = re.compile(r"【([^】]+)】")
CIRCLED = "①②③④⑤⑥⑦⑧⑨❶❷❸❹❺❻❼❽❾"
STRIP_CHARS = "*＊" + CIRCLED
# Skip themes that have no dictionary-lookupable word list.
SKIP_THEMES = {"字母表"}


def read_paragraphs():
    with zipfile.ZipFile(DOCX) as z, z.open("word/document.xml") as f:
        tree = ET.parse(f)
    for p in tree.getroot().iter(NS + "p"):
        texts = [t.text for t in p.iter(NS + "t") if t.text]
        line = "".join(texts).strip()
        if line:
            yield line


def tokenize(line: str):
    """Yield Chinese word tokens from a docx word-list line.

    Handles: `我、你、他/她/它`, `睡觉（居住）`, `兵（军）*`, `支出①`,
    nested separators inside parentheses, and filters out non-Chinese
    glosses like `（20）`, `（T恤）`.
    """
    # Split top-level on 、 while keeping parenthetical groups separate.
    depth = 0
    buf = []
    groups = []
    for ch in line:
        if ch in "（(":
            depth += 1
            buf.append(ch)
        elif ch in "）)":
            depth -= 1
            buf.append(ch)
        elif ch == "、" and depth == 0:
            groups.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        groups.append("".join(buf))

    for grp in groups:
        grp = grp.strip()
        if not grp:
            continue
        # Expand parenthetical synonyms as siblings of the head.
        m = re.match(r"^([^（(]*)[（(]([^）)]*)[）)](.*)$", grp)
        if m:
            head, inside, tail = m.group(1), m.group(2), m.group(3)
            parts = [head + tail] + re.split(r"[、,]", inside)
        else:
            parts = [grp]
        for p in parts:
            for sub in re.split(r"[/／]", p):
                token = sub.strip().strip(STRIP_CHARS).strip()
                if not token:
                    continue
                # Keep only tokens that contain at least one CJK char.
                if not re.search(r"[一-鿿]", token):
                    continue
                yield token


def parse_themes():
    current = None
    themes: dict[str, list[str]] = {}
    for line in read_paragraphs():
        m = THEME_RE.match(line)
        if m:
            name = m.group(1).strip()
            current = None if name in SKIP_THEMES else name
            if current and current not in themes:
                themes[current] = []
            # Line may contain trailing content after 】: strip the header
            # and fall through to tokenize the remainder.
            remainder = line[m.end():].strip()
            if current and remainder and not remainder.startswith("（"):
                themes[current].extend(tokenize(remainder))
            continue
        if current is None:
            continue
        # Skip pure parenthetical annotation lines.
        if line.startswith("（") and line.endswith("）"):
            continue
        themes[current].extend(tokenize(line))
    # Dedup preserving order.
    return {t: list(dict.fromkeys(ws)) for t, ws in themes.items()}


def main():
    themes = parse_themes()
    total_tokens = sum(len(v) for v in themes.values())
    print(f"Parsed {len(themes)} themes, {total_tokens} unique tokens")

    if os.path.exists(DST_DB):
        os.remove(DST_DB)
    shutil.copy2(SRC_DB, DST_DB)
    con = sqlite3.connect(DST_DB)
    cur = con.cursor()
    cur.execute("ALTER TABLE signs ADD COLUMN theme TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_signs_theme ON signs(theme)")

    matched_tokens = 0
    matched_signs = set()
    per_theme = []
    for theme, words in themes.items():
        t_sign_ids: set[int] = set()
        t_matched = 0
        t_missed = []
        for w in words:
            rows = cur.execute(
                "SELECT DISTINCT sign_id FROM meanings WHERE text = ?", (w,)
            ).fetchall()
            if rows:
                t_matched += 1
                t_sign_ids.update(r[0] for r in rows)
            else:
                t_missed.append(w)
        if t_sign_ids:
            cur.executemany(
                "UPDATE signs SET theme = COALESCE(theme || '|' || ?, ?) "
                "WHERE id = ? AND (theme IS NULL OR instr('|'||theme||'|', '|'||?||'|') = 0)",
                [(theme, theme, sid, theme) for sid in t_sign_ids],
            )
        matched_tokens += t_matched
        matched_signs.update(t_sign_ids)
        per_theme.append((theme, len(words), t_matched, len(t_sign_ids), t_missed))

    con.commit()
    con.close()

    print(f"\nMatched {matched_tokens}/{total_tokens} tokens, "
          f"tagged {len(matched_signs)} distinct signs\n")
    print(f"{'theme':<14}{'words':>7}{'hit':>6}{'signs':>7}  first 5 misses")
    print("-" * 80)
    for name, total, hit, nsigns, missed in per_theme:
        miss_preview = "、".join(missed[:5])
        print(f"{name:<14}{total:>7}{hit:>6}{nsigns:>7}  {miss_preview}")


if __name__ == "__main__":
    main()
