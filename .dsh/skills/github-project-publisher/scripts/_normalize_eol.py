"""把脚本目录下所有 .py/.md 文件归一化为 UTF-8 无 BOM + LF。

这是仓库内的一次性工具，属于脚本层自检的一部分：
DSH 文件沙箱与 Windows 编辑器都可能悄悄写入 CRLF，而 CRLF/BOM 会破坏
SHA256SUMS 的字节确定性。用法::

    python _normalize_eol.py [目录]
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

TARGET_SUFFIXES = (".py", ".md", ".txt", ".json")


def normalize(path: Path) -> bool:
    """返回 True 表示文件被改写。"""
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    text = raw.decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    data = text.encode("utf-8")
    if data == raw and not had_bom and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def main(argv) -> int:
    roots = [Path(arg) for arg in argv[1:]] or [Path(__file__).resolve().parent]
    changed = 0
    checked = 0
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in TARGET_SUFFIXES:
                continue
            checked += 1
            if normalize(path):
                changed += 1
                print("normalized: {0}".format(path.name))
    print("checked={0} changed={1}".format(checked, changed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
