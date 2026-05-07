# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**中国手语词典数据库** — extracts 《国家通用手语词典（全四册）》EPUBs into a base SQLite DB + flat image folder, plus a derivative theme-tagged DB with difficulty progression, for consumption by the sibling `signo-web` app.

> This folder is a sub-project of `/Users/wishingcat/Projects/Signo/`. That parent `CLAUDE.md` documents the Next.js app; this one documents only the data pipeline.

## Repo layout

```
sign-language-database/
├── DictionaryBook/       ← source: 4 EPUBs (Volume 1–4.epub). Do not modify.
├── scripts/
│   ├── extract_epub.py        ← base pipeline: EPUB → signs.db + images/
│   ├── add_themes.py          ← one-shot tag pass (docx → signs.theme); input docx removed from repo, kept for reference
│   ├── add_theme_order.py     ← writes `themes` table (difficulty_rank, tier) into sign_themed.db
│   └── build_progression.py   ← reads sign_themed.db → emits 主题难度进阶.md
├── images/               ← 6699 extracted sign images (v{N}_ prefixed)
├── signs.db              ← base DB (signs + meanings)
├── sign_themed.db        ← derivative: adds signs.theme column + themes table
└── 主题难度进阶.md        ← generated teaching-order view of sign_themed.db
```

## Rebuild commands — one per artifact

```bash
# 1. Base extraction (~10s; requires DictionaryBook/Volume {1..4}.epub)
rm -rf images signs.db && python3 scripts/extract_epub.py

# 2. Difficulty ordering + progression doc (operates on committed sign_themed.db)
python3 scripts/add_theme_order.py
python3 scripts/build_progression.py
```

Python 3.13 stdlib only; no deps. The base pipeline is idempotent.

**`sign_themed.db` is a committed snapshot, not a rebuildable artifact.** It was produced by `add_themes.py` from `手语词库主题分类（2025.2）.docx`, which is no longer in the repo. To re-derive tags from scratch, restore that docx at the repo root and run `add_themes.py`.

## Architecture — how the pipeline thinks about the source

The source EPUBs have a predictable shape per letter section. The parser exploits this and makes **no attempt** at general-purpose EPUB/HTML parsing:

1. **Volume detection** — iterate `DictionaryBook/Volume {1..4}.epub`, extract each to a tmp dir.
2. **Dictionary section detection** — a xhtml is a dict section iff its first `<h1 class="sect1">` is a single `A-Z` char, or the literal string `其他`. Preface/国歌/索引 files fail this test and are skipped automatically.
3. **Entry parsing** — split body on `<h2 class="sect2">`. For each chunk:
   - `<h2>` text before the `　` (U+3000) full-width space = Chinese header; everything after is pinyin (discarded).
   - First `<div class="picture_figure"><img src="...">` = the sign image.
   - All `<p class="content">` until next `<h2>` = description, joined by `\n`.
4. **Header decomposition** (`parse_header`) — takes cleaned Chinese head like `标题①（题目①、书名号）` and yields `[(text, variant_index, order)]` tuples. Splits on `（…）` then `、`.
5. **Variant stripping** (`parse_variant`) — trailing circled digit → numeric `variant_index`.

## Non-obvious decisions baked into the parser

- **Two coexisting circled-digit glyph sets** in the source: `①-⑨` (U+2460–2468) AND `❶-❾` (U+2776–277E). Both are mapped to `variant_index` 1–9 via `CIRCLED.index() % 9 + 1`. If you touch `CIRCLED`, keep both halves 9 chars.
- **Image namespacing** — the same filename (e.g. `txt005_2.jpg`) appears in multiple volumes with different content. Output images are prefixed `v{N}_` to prevent collisions. Never remove this prefix logic.
- **`letter='#'`** is reserved for the 其他 section (numbers 0–100, 千万亿, and abbrevs like 3D/CT/KTV/QQ/WIFI). `其他` entries legitimately contain ASCII in their head — do NOT apply any "strip pinyin by finding Latin char" heuristic, it will corrupt them.
- **Missing letters**: no I, U, or V — this matches real Chinese pinyin usage, not a bug.
- **`HEAD_OVERRIDES` dict at the top of the script** — 4 source-EPUB typos (missing `　` separator or missing `（`) that the parser cannot recover from. Keyed by the exact broken head string after tag-strip. Add a new row here when a new typo surfaces; do NOT add parser heuristics to "fix" typos generically.

## Schema — two tables

### `signs` — one row per sign (one image)

| 列 | 类型 | 含义 |
|---|---|---|
| `id` | INTEGER PK | 手势唯一 id |
| `image_path` | TEXT | `images/v{N}_...jpg`，相对路径 |
| `description` | TEXT | 打法文字；原书分步 `（一）`/`（二）` 用 `\n` 拼接 |
| `source_entry` | TEXT | 原书 h2 标题清洗版（去拼音、去 html），仅供溯源 |
| `letter` | TEXT | 首字母分区 `A`–`Z` 或 `#`（其他） |
| `volume` | INTEGER | 来自第几册（1–4） |

### `meanings` — one row per Chinese meaning; multiple rows may point to the same sign

| 列 | 类型 | 含义 |
|---|---|---|
| `id` | INTEGER PK | 自增 |
| `sign_id` | INTEGER FK → `signs.id` | 多个 meanings 共享同一 sign_id = 它们打法相同 |
| `text` | TEXT | 具体释义（已剥离 ①②，纯词面） |
| `variant_index` | INTEGER / NULL | ① → 1，② → 2，…；无变体标记为 `NULL` |
| `order_in_entry` | INTEGER | 原词条中位置，主词 = 0，括号内依次 1/2/… |

Indexes: `idx_signs_letter`, `idx_meanings_sign`, `idx_meanings_text`.

### Three data shapes the schema is designed around

**① 多释义共享一张图** — `爱人（丈夫、妻子、媳妇）`
```
signs     id=31 source_entry=爱人（丈夫、妻子、媳妇）
meanings  (31, 爱人, NULL, 0) (31, 丈夫, NULL, 1) (31, 妻子, NULL, 2) (31, 媳妇, NULL, 3)
```

**② 同一词多种打法** — `爱国①` / `爱国②` → two `signs` rows, two images
```
signs     id=25 source_entry=爱国①         id=26 source_entry=爱国②
meanings  (25, 爱国, 1, 0)                  (26, 爱国, 2, 0)
```

**③ 变体 + 多义混合** — `结账（买单、埋单、支出①、消费①、费）`
```
signs     id=… source_entry=结账（买单、埋单、支出①、消费①、费）
meanings  (…, 结账, NULL, 0) (…, 买单, NULL, 1) (…, 埋单, NULL, 2)
          (…, 支出, 1, 3)    (…, 消费, 1, 4)    (…, 费,   NULL, 5)
```

### Core invariants (preserve in any future change)

- Every `signs` row has a real file at `image_path` and a non-empty `description`.
- Multiple `meanings` sharing the same `sign_id` ⇔ those Chinese words share one sign.
- `爱国①` vs `爱国②` = **two** `signs` rows (different images), each with one `meanings` row whose `text='爱国'` and distinct `variant_index`.
- In `sign_themed.db`: every theme name appearing in `signs.theme` (split by `|`) must exist as a row in `themes.name`. `add_theme_order.py` enforces this on write and will refuse to commit if a referenced theme is missing.

### Common queries

```sql
-- 按中文词查手势
SELECT s.image_path, s.description
FROM meanings m JOIN signs s ON s.id = m.sign_id
WHERE m.text = '妻子';

-- 查某词的所有打法
SELECT m.variant_index, s.image_path
FROM meanings m JOIN signs s ON s.id = m.sign_id
WHERE m.text = '爱国' ORDER BY m.variant_index;

-- 找共享同一手势的同义词组
SELECT group_concat(text, '、') AS synonyms, sign_id
FROM meanings GROUP BY sign_id HAVING COUNT(*) > 1;
```

## Derivative DB — `sign_themed.db`

Two additions on top of the base schema; both live in this file only.

### `signs.theme` column (TEXT, indexed)

Pipe-separated list of theme names — e.g. `"生活"` or `"身体|爱心社"`. Currently 1213 of 6699 signs tagged; 52 carry multiple themes. `add_themes.py` wrote these by exact-matching each word in `手语词库主题分类（2025.2）.docx` against `meanings.text`; hit rate was 1243/1292 tokens. No semantic fallback — unmatched words were silently skipped. The tag pass is **not rerunnable in-repo** since the docx is gone; treat the committed `sign_themed.db` as authoritative.

Multi-theme rows mean the sign matched words listed under more than one theme in the docx (e.g. a medical-related sign tagged both `身体` and `爱心社`). App-side, either pre-split on `|` or add a normalized `sign_themes` relation — a plain `JOIN themes ON themes.name = signs.theme` will not match the multi-theme rows.

### `themes` table — difficulty ordering

```
themes(name TEXT PK, difficulty_rank INTEGER UNIQUE, tier TEXT)
  -- 31 rows, rank 1..31
  -- tier ∈ {入门, 初级, 中初, 中级, 中高, 高级, 专项}
```

**This table is the single source of truth for pedagogical order.** Don't hardcode the ordering anywhere else. `add_theme_order.py` defines the `TIERS` list at the top — to reorder/rename themes, edit that list and rerun it plus `build_progression.py`. Never hand-edit the DB — it'll drift from signs.db and be painful to regenerate.

Typical signo-web consumption:

```sql
-- Words for a given tier, in progression order
SELECT t.difficulty_rank, s.theme, m.text, s.image_path
FROM signs s
JOIN themes t   ON t.name = s.theme          -- see caveat about multi-theme
JOIN meanings m ON m.sign_id = s.id
WHERE t.tier = '入门'
ORDER BY t.difficulty_rank, s.id, m.order_in_entry;
```

### `主题难度进阶.md`

Human-readable view only — do not parse it. Regenerated from the DB by `build_progression.py`; every word shown comes from `meanings.text` (not from the docx). Same-sign-different-打法 words get ①② suffixes in the output.

## Extending

- **Adding another dictionary volume** — drop the EPUB in `DictionaryBook/`, add its number to `VOLUMES` at the top of `extract_epub.py`, rerun. Section detection is auto; no other code changes if its structure matches (single-letter `<h1 class="sect1">` + `<h2 class="sect2">` entries).
- **Different book with different HTML shape** — write a new parser; do not try to generalize this one. The tight coupling to class names (`sect1`/`sect2`/`picture_figure`/`content`) is intentional.
- **New dictionary fields** — add a column to `signs` (migration = just rerun; nothing persists between runs). Keep the 3-layer mental model: raw header → signs row → multiple meanings.
- **Re-order or rename difficulty tiers** — edit `TIERS` in `scripts/add_theme_order.py`, rerun it, then `build_progression.py`. The theme table is rebuilt from scratch each run (`DROP TABLE IF EXISTS`), so it's safe to iterate.
- **New themes / retag** — requires the source docx (not in repo). Restore it, edit `add_themes.py` if the docx structure changed, rerun against a fresh copy of `signs.db` → `sign_themed.db`, then redo the two theme-order commands.

## Validation after any parser change

Run the extraction, then sanity-check:

```bash
sqlite3 signs.db "SELECT COUNT(*) FROM signs;              -- expect 6699
SELECT COUNT(*) FROM meanings;                             -- expect 8687
SELECT COUNT(*) FROM signs WHERE description='';           -- expect 0
SELECT COUNT(*) FROM meanings WHERE text GLOB '*[①②③④⑤⑥⑦⑧⑨❶❷❸❹❺❻❼❽❾]*'; -- expect 0 (variant leakage canary)"
```

The last query is the key canary — if nonzero, either a new glyph set appeared or a new typo case needs a `HEAD_OVERRIDES` entry.

After `add_theme_order.py` (sanity-checks the themed DB):

```bash
sqlite3 sign_themed.db "
  SELECT COUNT(*) FROM themes;                         -- expect 31
  SELECT COUNT(*) FROM signs WHERE theme IS NOT NULL;  -- expect 1213
  SELECT COUNT(*) FROM signs WHERE theme LIKE '%|%';   -- expect 52 (multi-theme rows)
"
```
