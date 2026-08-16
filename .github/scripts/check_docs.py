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
FUKI = re.compile(r"付記は\s*\*?\*?(\d+)字（(\d+)〜(\d+)）")


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

    # 許容幅が目安の ±10% と食い違っていないか（端数は ±5字まで許容）
    for num, target, lo, hi in rows:
        want_lo, want_hi = round(target * 0.9), round(target * 1.1)
        if abs(lo - want_lo) > 5 or abs(hi - want_hi) > 5:
            err(
                f"{KATA}: 段落{num} の許容幅 {lo}〜{hi} が目安 {target}字 の±10%"
                f"（{want_lo}〜{want_hi}）と合いません"
            )

    m = BAND.search(text)
    if not m:
        err(f"{KATA}: 合計の帯（合計は◯〜◯字）が見つかりません")
        return
    band_lo, band_hi = (int(x.replace(",", "")) for x in m.groups())
    total = sum(r[1] for r in rows) + (int(FUKI.search(text).group(1)) if FUKI.search(text) else 0)
    if not band_lo <= total <= band_hi:
        err(
            f"{KATA}: 段落の目安の合計 {total}字 が、帯 {band_lo}〜{band_hi}字 の外です"
        )

    # 許容幅をすべて上限（下限）に寄せると、合計の帯を外れることがある。
    # 各段落が許容幅に収まっていても合計が帯を外れる状態を、型が説明しているか見る。
    # 付記（性別の断り・締めの一文）は段落表の外にあるが、本文の字数に入る。
    # 枠を置かないと、段落が全部収まっていても合計が帯を超える。
    fu = FUKI.search(text)
    fu_mid, fu_lo, fu_hi = (
        (int(fu.group(1)), int(fu.group(2)), int(fu.group(3))) if fu else (0, 0, 0)
    )
    if not fu:
        err(f"{KATA}: 付記の字数の枠（付記は◯字（◯〜◯））が見つかりません")

    sum_hi = sum(r[3] for r in rows) + fu_hi
    sum_lo = sum(r[2] for r in rows) + fu_lo
    if sum_hi > band_hi or sum_lo < band_lo:
        if "合計の帯が優先" not in text:
            err(
                f"{KATA}: 許容幅の合計（{sum_lo}〜{sum_hi}字）が帯"
                f"（{band_lo}〜{band_hi}字）からはみ出します。"
                "各段落が許容幅に収まっても合計が帯を外れるため、"
                "どちらが優先するかを型に明記してください（「合計の帯が優先」）"
            )


# ------------------------------------------- 5. 型と担当のあいだの食い違い（エラー）
AGENTS = [
    ".claude/agents/coconala-kantei.md",
    ".claude/agents/coconala-kantei-checker.md",
]

PARA_COUNT_CITE = re.compile(r"型の(\d+)段落")
TOLERANCE = re.compile(r"目安の\*\*±(\d+)%\*\*")
TOLERANCE_CITE = re.compile(r"許容幅は目安の±(\d+)%")
BAND_CITE = re.compile(r"合計\s*(\d[\d,]*)〜(\d[\d,]*)字")
HALF_KATA = re.compile(r"吉凶が相半ばする数（\d+）\**\s*：\s*([0-9,\s]+)")
HALF_CITE = re.compile(r"相半ばの数\**\s*（([0-9０-９・\s]+)）")

Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def check_kata_vs_agents() -> None:
    """型が決めた数字を、担当の手順書が古いまま引用していないか。

    型を直したのに担当への反映が漏れる、という食い違いが実際に3回起きた。
    節やファイルをまたぐため、ファイル単位の点検では拾えない。
    """
    kata = read(KATA)
    if kata is None:
        return

    facts: dict[str, object] = {}

    n_para = len([ln for ln in kata.splitlines() if PARA_ROW.match(ln)])
    if n_para:
        facts["段落数"] = n_para

    m = TOLERANCE.search(kata)
    if m:
        facts["許容幅の割合"] = int(m.group(1))

    m = BAND.search(kata)
    if m:
        facts["帯"] = tuple(int(x.replace(",", "")) for x in m.groups())

    m = HALF_KATA.search(kata)
    if m:
        facts["相半ばの数"] = {int(x) for x in re.findall(r"\d+", m.group(1))}

    for rel in AGENTS:
        text = read(rel)
        if text is None:
            continue
        body = strip_records(text)

        for m in PARA_COUNT_CITE.finditer(body):
            if "段落数" in facts and int(m.group(1)) != facts["段落数"]:
                err(
                    f"{rel}: 「型の{m.group(1)}段落」とありますが、"
                    f"型の段落は{facts['段落数']}です"
                )

        for m in TOLERANCE_CITE.finditer(body):
            if "許容幅の割合" in facts and int(m.group(1)) != facts["許容幅の割合"]:
                err(
                    f"{rel}: 許容幅を±{m.group(1)}%としていますが、"
                    f"型は±{facts['許容幅の割合']}%です"
                )

        for m in BAND_CITE.finditer(body):
            got = tuple(int(x.replace(",", "")) for x in m.groups())
            if "帯" in facts and got != facts["帯"]:
                err(
                    f"{rel}: 合計の帯を{got[0]:,}〜{got[1]:,}字としていますが、"
                    f"型は{facts['帯'][0]:,}〜{facts['帯'][1]:,}字です"
                )

        for m in HALF_CITE.finditer(body):
            got = {int(x) for x in m.group(1).translate(Z2H).split("・") if x.strip()}
            if "相半ばの数" in facts and got != facts["相半ばの数"]:
                err(
                    f"{rel}: 相半ばの数を{sorted(got)}としていますが、"
                    f"型は{sorted(facts['相半ばの数'])}です"
                )


# ------------------------------------- 6. 廃止した書き方が残っていないか（エラー）
# 型が「使わない」と決めたもの。運用部分（記録・追記ログ以外）に出たらエラー。
RETIRED = [
    (re.compile(r"\d+\s*〜?\s*\d*\s*歳"), "各格に年齢を割り当てない（型2節）"),
    (re.compile(r"(主運|副運|前運|後運)"), "この呼称は使わない（型0節）"),
]

RECORD_HEADING = re.compile(r"^#+.*(記録|廃止|追記ログ|削除|直した|過去|失敗|経緯|訂正)")
ANY_HEADING = re.compile(r"^#+\s")

# 廃止したものは、記録として書き残すことになっている。
# 見出しだけでは記録か指示かを判別できないため、文そのものの書き方でも見る。
# 完全ではない。「以前は◯歳としていた」と書けば通るので、人の点検は要る。
RECORD_SENTENCE = re.compile(
    r"(廃止|使わない|使わなくなった|やめ[たるる]?|以前|かつて|過去|取り下げ|"
    r"差し替え|誤り|直した|していた|だった|残っていた|書いていた|見直す)"
)


def strip_records(text: str) -> str:
    """記録・廃止・追記ログの節と、引用ブロックを落とす。

    廃止したものは、記録として書き残すことになっている。
    記録に出るのは正しいので、指示として書かれている箇所だけを見る。
    """
    out, skipping = [], False
    for ln in text.splitlines():
        if ANY_HEADING.match(ln):
            skipping = bool(RECORD_HEADING.match(ln))
        if skipping or ln.lstrip().startswith(">") or ln.lstrip().startswith("|"):
            continue
        if RECORD_SENTENCE.search(ln):
            continue
        out.append(ln)
    return "\n".join(out)


def check_retired_wording() -> None:
    for rel in [KATA, *AGENTS]:
        text = read(rel)
        if text is None:
            continue
        for pat, why in RETIRED:
            for m in pat.finditer(strip_records(text)):
                err(f"{rel}: 「{m.group(0)}」が指示として残っています — {why}")


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
    check_kata_vs_agents()
    check_retired_wording()
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
