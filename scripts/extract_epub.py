#!/usr/bin/env python3
"""Extract China Sign Language Dictionary (all 4 volumes) from EPUB to SQLite.

Detects dictionary sections by h1.sect1: single A-Z letter, or '其他' (→ letter='#').
Images are namespaced by volume prefix (v{N}_...) to avoid filename collisions.

Schema:
  signs(id, image_path, description, source_entry, letter, volume)
  meanings(id, sign_id, text, variant_index, order_in_entry)
"""
import html
import os
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "DictionaryBook"
WORK = ROOT / ".epub_work"
IMG_DIR = ROOT / "images"
DB = ROOT / "signs.db"
VOLUMES = [1, 2, 3, 4]
CIRCLED = "①②③④⑤⑥⑦⑧⑨❶❷❸❹❺❻❼❽❾"  # two coexisting glyph sets in the book

# Source-EPUB typos: missing 　 separator or missing （. Map raw h2 head → cleaned head.
HEAD_OVERRIDES = {
    "困难②（艰难②、伤脑筋②）kùn·nan ②（jiānnán ②、shāng nǎojīn ②）": "困难②（艰难②、伤脑筋②）",
    "命运❷mìngyùn ❷": "命运❷",
    "要么……要么……①是……还是……②）": "要么……要么……①（是……还是……②）",
    "瘾②（上瘾②、成瘾②） yǐn②（shàngyǐn ②、chéngyǐn②）": "瘾②（上瘾②、成瘾②）",
}


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def detect_letter(xhtml_path: Path):
    text = xhtml_path.read_text(encoding="utf-8")
    m = re.search(r'<h1[^>]*class="sect1"[^>]*>([^<]+)</h1>', text)
    if not m:
        return None
    h1 = m.group(1).strip()
    if re.fullmatch(r"[A-Z]", h1):
        return h1
    if h1 == "其他":
        return "#"
    return None


def parse_variant(text: str):
    m = re.match(rf"^(.+?)([{CIRCLED}])$", text)
    if m:
        return m.group(1), CIRCLED.index(m.group(2)) % 9 + 1
    return text, None


def parse_header(head_text: str):
    head_text = head_text.strip()
    m = re.match(r"^([^（]+)(?:（([^）]+)）)?$", head_text)
    if not m:
        return [(head_text, None, 0)]
    main = m.group(1).strip()
    alts = m.group(2)
    parts = [main] + ([p.strip() for p in alts.split("、") if p.strip()] if alts else [])
    out = []
    for i, p in enumerate(parts):
        base, variant = parse_variant(p)
        out.append((base.strip(), variant, i))
    return out


def parse_entries(xhtml_path: Path):
    content = xhtml_path.read_text(encoding="utf-8")
    body = re.search(r"<body>(.*?)</body>", content, re.DOTALL).group(1)
    for ch in re.split(r'(?=<h2[^>]*class="sect2")', body):
        if not ch.lstrip().startswith("<h2"):
            continue
        h2m = re.match(r"<h2[^>]*>(.*?)</h2>", ch.lstrip(), re.DOTALL)
        if not h2m:
            continue
        head_html = h2m.group(1).split("　")[0]
        head = html.unescape(strip_tags(head_html)).strip()
        if head in HEAD_OVERRIDES:
            head = HEAD_OVERRIDES[head]
        if not head:
            continue
        img_m = re.search(
            r'<div[^>]*class="picture_figure"[^>]*>\s*<img[^>]*src="([^"]+)"', ch
        )
        if not img_m:
            continue
        paras = re.findall(r'<p[^>]*class="content"[^>]*>(.*?)</p>', ch, re.DOTALL)
        desc = "\n".join(
            p for p in (html.unescape(strip_tags(x)).strip() for x in paras) if p
        )
        yield head, img_m.group(1), desc


def extract_volume(vol: int) -> Path:
    dst = WORK / f"v{vol}"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    with zipfile.ZipFile(BOOKS / f"Volume {vol}.epub") as z:
        z.extractall(dst)
    return dst


def init_db():
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.executescript(
        """
        CREATE TABLE signs (
          id INTEGER PRIMARY KEY,
          image_path TEXT NOT NULL,
          description TEXT NOT NULL,
          source_entry TEXT,
          letter TEXT NOT NULL,
          volume INTEGER NOT NULL
        );
        CREATE TABLE meanings (
          id INTEGER PRIMARY KEY,
          sign_id INTEGER NOT NULL REFERENCES signs(id),
          text TEXT NOT NULL,
          variant_index INTEGER,
          order_in_entry INTEGER
        );
        CREATE INDEX idx_meanings_text ON meanings(text);
        CREATE INDEX idx_meanings_sign ON meanings(sign_id);
        CREATE INDEX idx_signs_letter ON signs(letter);
        """
    )
    return conn


def main():
    WORK.mkdir(exist_ok=True)
    IMG_DIR.mkdir(exist_ok=True)
    conn = init_db()
    stats = []
    for vol in VOLUMES:
        vol_root = extract_volume(vol)
        ops = vol_root / "OPS"
        src_imgs = ops / "images"
        dict_files = []
        for xhtml in sorted(ops.glob("txt*.xhtml")):
            letter = detect_letter(xhtml)
            if letter:
                dict_files.append((letter, xhtml))
        for letter, xhtml in dict_files:
            n_signs_letter = 0
            n_meanings_letter = 0
            for head, img_src, desc in parse_entries(xhtml):
                img_name = os.path.basename(img_src)
                dst_name = f"v{vol}_{img_name}"
                dst_path = IMG_DIR / dst_name
                if not dst_path.exists():
                    src = src_imgs / img_name
                    if src.exists():
                        shutil.copy2(src, dst_path)
                cur = conn.execute(
                    "INSERT INTO signs (image_path, description, source_entry, letter, volume) VALUES (?,?,?,?,?)",
                    (f"images/{dst_name}", desc, head, letter, vol),
                )
                sid = cur.lastrowid
                n_signs_letter += 1
                for base, variant, order in parse_header(head):
                    conn.execute(
                        "INSERT INTO meanings (sign_id, text, variant_index, order_in_entry) VALUES (?,?,?,?)",
                        (sid, base, variant, order),
                    )
                    n_meanings_letter += 1
            stats.append((vol, letter, n_signs_letter, n_meanings_letter))
    conn.commit()
    conn.close()
    shutil.rmtree(WORK)
    tot_s = sum(s for _, _, s, _ in stats)
    tot_m = sum(m for _, _, _, m in stats)
    for v, L, s, m in stats:
        print(f"  Vol {v}  {L}: signs={s}  meanings={m}")
    print(f"TOTAL  signs={tot_s}  meanings={tot_m}")


if __name__ == "__main__":
    main()
