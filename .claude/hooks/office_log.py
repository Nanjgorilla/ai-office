#!/usr/bin/env python3
"""バーチャルオフィスに「いま誰が何をしているか」を流す記録係。

Claude Code のフックから呼ばれ、標準入力で受け取った出来事を
`office/activity.jsonl` に1行ずつ追記する。平面図（office/index.html）が
このファイルを読んで、席の灯りと書類の動きに変える。

## 本文は残さない

このリポジトリにはお客様の実名を一切残さない決まりがある（全社ルールおよび
departments/coconala/CLAUDE.md）。依頼文・鑑定文・下書きの中身は、
お名前を含みうる。だからここでは**内容を一切書かない**。

残すのは、出来事の種類・担当者の名前・道具の名前・ファイルの場所・文字数だけ。
「誰が」「何をしていたか」は分かるが、「何と書いたか」は分からない。
それで平面図は十分に動く。

`office/activity.jsonl` 自体も `.gitignore` に入れてあり、commit されない。

## 止めない

記録に失敗しても、進行中の仕事を止めてはいけない。
何が起きても終了コード 0 で戻る。
"""

import datetime
import json
import os
import sys
from pathlib import Path

# 出来事の種類。平面図の側でこの名前を見て動きを決める。
# 依頼 / 指示 / 報告 は席から席へ書類が飛ぶ。それ以外はその席の中の動き。

TOOL_KIND = {
    "Task": "指示",
    "Write": "執筆",
    "Edit": "執筆",
    "NotebookEdit": "執筆",
    "Read": "調べ物",
    "Grep": "調べ物",
    "Glob": "調べ物",
    "WebSearch": "外出",
    "WebFetch": "外出",
    "Bash": "手作業",
}


def project_dir() -> Path:
    d = os.environ.get("CLAUDE_PROJECT_DIR")
    if d:
        return Path(d)
    return Path(__file__).resolve().parents[2]


def relative(root: Path, raw: str) -> str:
    """ファイルの場所を、リポジトリからの相対パスにする。

    リポジトリの外なら場所そのものを残さない（外の事情を持ち込まないため）。
    """
    if not raw:
        return ""
    try:
        p = Path(raw).resolve()
        return p.relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return "（リポジトリ外）"


def build(data: dict, root: Path) -> dict | None:
    event = data.get("hook_event_name", "")
    tool = data.get("tool_name", "") or ""
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if event == "SessionStart":
        return {"kind": "出社", "actor": "秘書役"}

    if event == "UserPromptSubmit":
        # 依頼の中身は書かない。長さだけ残す。
        prompt = data.get("prompt") or ""
        return {
            "kind": "依頼",
            "actor": "依頼主",
            "to": "秘書役",
            "chars": len(prompt),
        }

    if event == "PreToolUse":
        if tool == "Task":
            return {
                "kind": "指示",
                "actor": "秘書役",
                "to": tool_input.get("subagent_type") or "客員",
            }
        return {
            "kind": TOOL_KIND.get(tool, "手作業"),
            "tool": tool,
            "path": relative(root, tool_input.get("file_path") or ""),
        }

    if event == "PostToolUse":
        if tool == "Task":
            return {
                "kind": "報告",
                "actor": tool_input.get("subagent_type") or "客員",
                "to": "秘書役",
            }
        if tool in ("Write", "Edit", "NotebookEdit"):
            return {
                "kind": "保管",
                "path": relative(root, tool_input.get("file_path") or ""),
            }
        return None

    if event == "Notification":
        return {"kind": "呼び出し", "actor": "秘書役"}

    if event == "Stop":
        return {"kind": "手待ち", "actor": "秘書役"}

    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0

    root = project_dir()
    try:
        record = build(data, root)
    except Exception:  # 記録係の都合で仕事を止めない
        return 0
    if record is None:
        return 0

    record["t"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    record["session"] = (data.get("session_id") or "")[:8]

    try:
        out = root / "office" / "activity.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
