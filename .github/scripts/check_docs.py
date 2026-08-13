#!/usr/bin/env python3
"""AIオフィスのルール文書を機械的に点検する。

人が毎回目で確認していた項目のうち、機械で判定できるものだけを扱う。
字数の実測や「否定形テスト」のような判断は、人と点検役の仕事なのでここには入れない。

使い方:
    python3 .github/scripts/check_docs.py [base_ref]

base_ref を渡すと、その時点からの差分を見て「変更したのに追記ログを更新していない」
を検出する。省略すると、そのチェックだけを飛ばす。
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KATA = "departments/coconala/鑑定の型.md"

# 追記ログを持つべきファイル
LOGGED_FILES = [
    KATA,
    "departments/coconala/CLAUDE.md",
    ".claude/agents/coconala-kantei.md",
    ".claude/agents/coconala-kantei-checker.md",
    ".claude/agents/coconala-kantei-reviewer.md",
    ".claude/agents/coconala-researcher.md",
    ".claude/agents/coconala-writer.md",
]

# 免責文の冒頭。鑑定の型.md 以外でこれが出たら、鑑定文が commit されたということ
DISCLAIMER_HEAD = "姓名判断は、お名前という一つの切り口から人となりを読み解くものです。"

LOG_LINE = re.compile(r"^-\s*\[(\d{4}-\d{2}-\d{2})\]")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def read(rel: str) -> str | None:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else None


# ---------------------------------------------------------------- 1. 個人情報
def check_no_kantei_committed() -> None:
    """鑑定文がリポジトリに commit されていないか。

    お客様の実名を残さないため、鑑定担当には書き込み権限を持たせていない。
    それでも人の手で貼り付けられる可能性があるので、ここで止める。
    免責文は毎回同じ文言なので、これが型の外に出たら鑑定文が入った合図になる。
    """
    for path in ROOT.rglob("*.md"):
        if ".git/" in str(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == KATA:
            continue
        if DISCLAIMER_HEAD in path.read_text(encoding="utf-8"):
            err(
                f"{rel}: 免責文が含まれています。鑑定文が commit された可能性があります。"
                f"お客様の実名がリポジトリに残っていないか確認してください"
            )


# ---------------------------------------------------------------- 2. 追記ログ
def check_changelog_exists() -> None:
    for rel in LOGGED_FILES:
        text = read(rel)
        if text is None:
            err(f"{rel}: ファイルが見つかりません")
            continue
        if not re.search(r"^#+\s*(ルールの)?追記ログ", text, re.M):
            err(f"{rel}: 追記ログの節がありません")
        elif not any(LOG_LINE.match(ln) for ln in text.splitlines()):
            err(f"{rel}: 追記ログに [YYYY-MM-DD] 形式の行がありません")


def count_log_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if LOG_LINE.match(ln))


def check_changelog_updated(base_ref: str) -> None:
    """変更したのに追記ログを更新していないファイルを検出する。

    全社ルール1「言われなくても記録する」の機械チェック版。
    """
    try:
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
    except subprocess.CalledProcessError:
        warn(f"{base_ref} との差分が取得できず、追記ログの更新チェックを飛ばしました")
        return

    for rel in LOGGED_FILES:
        if rel not in changed:
            continue
        try:
            before = subprocess.run(
                ["git", "show", f"{base_ref}:{rel}"],
                cwd=ROOT, capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue  # 新規ファイル
        after = read(rel) or ""
        if count_log_lines(after) <= count_log_lines(before):
            err(f"{rel}: 変更されていますが、追記ログに行が増えていません")


# ------------------------------------------------------------ 3. 型の内部整合
PARA_ROW = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*(\d+)字\s*\|\s*(\d+)〜(\d+)\s*\|")
BAND = re.compile(r"合計は\s*\*?\*?([\d,]+)〜([\d,]+)字")


def check_kata_consistency() -> None:
    text = read(KATA)
    if text is None:
        return

    rows = [
        (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        for m in (PARA_ROW.match(ln) for ln in text.splitlines())
        if m
    ]
    if not rows:
        err(f"{KATA}: 段落ごとの目安表が見つかりません")
        return

    nums = [r[0] for r in rows]
    if nums != list(range(1, len(nums) + 1)):
        err(f"{KATA}: 段落番号が連番になっていません（{nums}）")

    # 許容幅が目安の ±20% と食い違っていないか（端数は ±5字まで許容）
    for num, target, lo, hi in rows:
        want_lo, want_hi = round(target * 0.8), round(target * 1.2)
        if abs(lo - want_lo) > 5 or abs(hi - want_hi) > 5:
            err(
                f"{KATA}: 段落{num} の許容幅 {lo}〜{hi} が目安 {target}字 の±20%"
                f"（{want_lo}〜{want_hi}）と合いません"
            )

    m = BAND.search(text)
    if not m:
        err(f"{KATA}: 合計の帯（合計は◯〜◯字）が見つかりません")
        return
    band_lo, band_hi = (int(x.replace(",", "")) for x in m.groups())
    total = sum(r[1] for r in rows)
    if not band_lo <= total <= band_hi:
        err(
            f"{KATA}: 段落の目安の合計 {total}字 が、帯 {band_lo}〜{band_hi}字 の外です"
        )


# ------------------------------------------------------- 4. 英単語の混入（警告）
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
CODE_SPAN = re.compile(r"`[^`]*`")
CODE_BLOCK = re.compile(r"```.*?```", re.S)
URL = re.compile(r"https?://\S+")
ASCII_WORD = re.compile(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])")

ALLOWED = {
    "AI", "GitHub", "Markdown", "YYYY", "MM", "DD", "OK", "NG", "URL",
    "CLAUDE", "md", "coconala", "kantei", "checker", "reviewer",
    "researcher", "writer", "inbox", "departments", "secretary",
    # サブエージェントに与える道具の名前
    "Read", "Grep", "Glob", "Write", "WebSearch", "WebFetch",
}

LOG_HEADING = re.compile(r"^#+\s*(ルールの)?追記ログ", re.M)


def check_no_stray_english() -> None:
    """日本語の文中に英単語が紛れていないか。

    以前 especially / good / tension が本文に混ざっていたため。
    コード表記・URL・フロントマターは除外する。
    追記ログも除外する。「especially を修正した」という記録が残るのが正しいので、
    ここを見ると直したこと自体が違反として挙がってしまう。
    判定を誤ることがあるので、失敗にはせず警告にとどめる。
    """
    for rel in [KATA, "departments/coconala/CLAUDE.md"] + [
        f for f in LOGGED_FILES if f.startswith(".claude/")
    ]:
        text = read(rel)
        if text is None:
            continue
        if m := LOG_HEADING.search(text):
            text = text[: m.start()]
        text = FRONTMATTER.sub("", text)
        text = CODE_BLOCK.sub("", text)
        text = CODE_SPAN.sub("", text)
        text = URL.sub("", text)
        found = {w for w in ASCII_WORD.findall(text) if w not in ALLOWED}
        if found:
            warn(f"{rel}: 英単語が混ざっているかもしれません → {', '.join(sorted(found))}")


# ---------------------------------------------------------------------- main
def main() -> int:
    check_no_kantei_committed()
    check_changelog_exists()
    check_kata_consistency()
    check_no_stray_english()
    if len(sys.argv) > 1 and sys.argv[1]:
        check_changelog_updated(sys.argv[1])

    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"エラー: {e}")

    if errors:
        print(f"\n{len(errors)}件のエラーがあります。")
        return 1
    print(f"点検を通過しました（警告 {len(warnings)}件）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
