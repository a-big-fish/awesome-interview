"""Print the text of a PDF supplied on the command line (exploration only)."""

import sys
from pathlib import Path

import pymupdf


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: uv run python test/pypupdf.py <PDF 文件>")
        return 2
    with pymupdf.open(Path(sys.argv[1])) as document:
        for page in document:
            print(page.get_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
