#!/usr/bin/env python3
"""記事ファイルを、noteの編集画面に貼り付けられる形に変換する。

noteの編集画面はMarkdownをそのまま解釈しない。`##` や `**` を貼ると記号が残る。
そこで記号を落とし、無料パートと有料パートを分け、
どの行を見出しにするかの一覧を付けたものを出す。

貼る順番どおりに並べる。人は上から順になぞるだけでよい。

使い方:
    python3 departments/note/貼り付け用に変換.py [YYYY-MM-DD]

日付を省くと、departments/note/ にある最新の記事ファイルを使う。
"""

import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
PAY_MARK = "ここから有料"
PRICE = "100円"


def pick_source(arg: str | None) -> Path:
    if arg:
        p = DIR / f"{arg}_記事.md"
        if not p.exists():
            sys.exit(f"{p.name} が見つかりません")
        return p
    files = sorted(DIR.glob("*_記事.md"))
    if not files:
        sys.exit(f"{DIR} に記事ファイルがありません")
    return files[-1]


def section(block: str, name: str, to_end: bool = False) -> str:
    """`### 名前` の中身を取り出す。

    既定では次の `###` の手前まで。本文は中に `###` の小見出しを含むので、
    to_end を立ててブロックの終わりまで取る。
    """
    if to_end:
        m = re.search(rf"^### {name}\n(.*)\Z", block, re.S | re.M)
    else:
        m = re.search(rf"^### {name}\n(.*?)(?=^### |\Z)", block, re.S | re.M)
    return m.group(1).strip() if m else ""


def to_plain(md: str) -> tuple[str, list[str], list[str]]:
    """Markdownを素のテキストにする。見出しと引用の行は別に返す。"""
    headings: list[str] = []
    quotes: list[str] = []
    out: list[str] = []

    for line in md.split("\n"):
        if m := re.match(r"^#{3,4} (.+)$", line):
            text = m.group(1).strip()
            headings.append(text)
            out.append(text)
            continue
        if m := re.match(r"^> ?(.*)$", line):
            text = m.group(1).strip()
            if text:
                quotes.append(text)
            out.append(text)
            continue
        line = line.replace("**", "")            # 太字の記号
        line = re.sub(r"^- ", "・", line)         # 箇条書き
        line = re.sub(r"^\*\*?", "", line)
        out.append(line)

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, headings, quotes


def fence(body: str) -> str:
    return f"```\n{body}\n```"


def convert(src: Path) -> str:
    raw = src.read_text(encoding="utf-8")
    date = src.name.split("_")[0]

    # 点検欄より後ろは記事ではない
    body_only = raw.split("\n## 公開前の点検")[0]
    parts = re.split(r"\n## (\d)本目 ── (\S+)\n", body_only)

    lines = [
        f"# {date} note貼り付け用（{PRICE}記事5本）",
        "",
        f"`{src.name}` から機械的に変換したもの。**手で直さない。**",
        "直すときは記事ファイルを直して、変換をかけ直す。",
        "",
        "各記事、番号どおりに上から操作すれば投稿画面が埋まる。",
        "**公開ボタンは人が押す。** 時間をずらしたいときはnoteの予約投稿を使う。",
        "",
        "太字は落としてある。noteの編集画面はMarkdownの記号をそのまま残すため。",
        "必要なら貼ったあとに当てる。見出しにする行は各記事の⑤に並べてある。",
        "",
    ]

    for i in range(1, len(parts), 3):
        num, waku, block = parts[i], parts[i + 1], parts[i + 2]
        title = section(block, "タイトル")
        tags = section(block, "ハッシュタグ")
        body = section(block, "本文", to_end=True)

        if PAY_MARK not in body:
            sys.exit(f"{num}本目に有料ラインが見つかりません")
        free_md, paid_md = re.split(rf"^.*{PAY_MARK}.*$", body, maxsplit=1, flags=re.M)

        free, h_free, q_free = to_plain(free_md)
        paid, h_paid, q_paid = to_plain(paid_md)
        headings, quotes = h_free + h_paid, q_free + q_paid

        lines += [
            "---",
            "",
            f"## {num}本目 ── {waku}",
            "",
            f"- 価格：{PRICE}",
            f"- ハッシュタグ：{tags}",
            "",
            "### ① タイトル欄に貼る",
            "",
            fence(title),
            "",
            "### ② 本文（無料パート）を貼る",
            "",
            fence(free),
            "",
            "### ③ ここで有料エリアを入れる",
            "",
            "本文のいちばん下にカーソルを置き、noteの編集画面から有料エリアを挿入する。",
            f"価格は{PRICE}。",
            "",
            "### ④ 有料エリアの中に貼る",
            "",
            fence(paid),
            "",
            "### ⑤ 書式を当てる",
            "",
            "次の行を選んで「小見出し」にする。",
            "",
        ]
        lines += [f"{n}. {h}" for n, h in enumerate(headings, 1)]
        lines.append("")
        if quotes:
            lines += ["次の行を「引用」にする。", ""]
            lines += [f"- {q}" for q in quotes]
            lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    src = pick_source(sys.argv[1] if len(sys.argv) > 1 else None)
    out = src.with_name(src.name.replace("_記事.md", "_貼り付け用.md"))
    out.write_text(convert(src), encoding="utf-8")
    print(f"{src.name} → {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
