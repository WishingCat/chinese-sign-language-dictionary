# Chinese Sign Language Dictionary (Derivative Dataset)

中国通用手语词典的结构化数据集 — 从《国家通用手语词典（全四册）》抽取，整理为 SQLite 数据库 + 手势图片集合。

## ⚠️ 版权声明 · License & Disclaimer

**本仓库仅供学习、研究与无障碍技术开发等非商业用途使用。**

- 本数据集为《国家通用手语词典（全四册）》的衍生作品。原书及其图文内容的版权归原出版方、编制单位及相关权利人所有。
- 本仓库**不包含**原书 EPUB / PDF 文件，仅包含经程序抽取并结构化的数据和图片。
- **禁止**将本数据集用于任何商业用途（包括但不限于付费 App、商业培训、再销售等）。
- 如果您是版权方，认为本仓库内容侵犯了您的合法权益，请通过 GitHub issue 或 [@WishingCat](https://github.com/WishingCat) 联系，我会在收到通知后**立即删除**相关内容。

**This repository is for non-commercial use only** (research, education, accessibility tooling). The data is derived from *National Common Chinese Sign Language Dictionary*; all rights to the original content belong to its publishers and compilers. Raw source books are NOT included. Commercial use is not permitted. Copyright holders may request takedown via issue or by contacting [@WishingCat](https://github.com/WishingCat).

## 内容 · Contents

| 文件 / 目录 | 说明 |
|---|---|
| `signs.db` | SQLite 数据库，2.0 MB，两张表（`signs`, `meanings`） |
| `images/` | 6699 张手势图（PNG/JPG），~350 MB |
| `scripts/extract_epub.py` | 抽取管线，Python 3 stdlib，无外部依赖 |
| `CLAUDE.md` | 架构文档：schema、数据形态、解析决策、常用查询 |

## 数据规模

- 手势条目（signs）: **6699**
- 中文释义（meanings）: **8687**
- 首字母分区: 24（A-F / G-M / N-X / Y Z #；无 I/U/V，符合拼音实际）
- 带变体 ①②/❶❷ 的手势: 806

## Schema 速览

```
signs    (id, image_path, description, source_entry, letter, volume)
meanings (id, sign_id → signs.id, text, variant_index, order_in_entry)
```

详细列级说明、三类典型数据形态（多释义同图 / 同词多打法 / 变体+多义混合）、以及常用查询，见 [`CLAUDE.md`](./CLAUDE.md)。

## 快速上手

```bash
# 按中文词查手势图与打法描述
sqlite3 signs.db "
  SELECT s.image_path, s.description
  FROM meanings m JOIN signs s ON s.id = m.sign_id
  WHERE m.text = '妻子';
"
```

## 重建数据（需要你自备 EPUB 源文件）

本仓库不含源书。如果你合法持有 4 册 EPUB，可放入 `DictionaryBook/Volume 1..4.epub`，然后：

```bash
python3 scripts/extract_epub.py
```

约 10 秒产出 `signs.db` 与 `images/`。管线细节见 `CLAUDE.md`。
