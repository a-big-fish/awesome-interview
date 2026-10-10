"""批量简历证件照识别工具（PyMuPDF 探索脚本，非生产入口）。

用法：
    .venv\Scripts\python test/pypupdf_pic.py [目标路径]

- 目标路径可以是单个 PDF，也可以是包含多个 PDF 的目录（递归查找）。
- 控制台只输出每份简历「照片: 有/无」以及最终统计；
  详细识别过程与报错统一写入 data/logs/resume_parser.log。
"""

import shutil
import sys
from pathlib import Path

from app.service.resume_parser_service import ResumeParserService

# 把识别出的照片复制到这里，方便人工核对；不需要可改为 None。
PHOTO_OUTPUT_DIR = Path(__file__).parent / "candidate_photos"


def _collect_pdfs(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.rglob("*.pdf"))
    if target.is_file():
        return [target]
    return []


def _dump_photo(resume, pdf_name: str) -> None:
    if not PHOTO_OUTPUT_DIR or not resume.candidate_photo_id:
        return
    for image in resume.images:
        if image.image_id == resume.candidate_photo_id:
            PHOTO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            target = PHOTO_OUTPUT_DIR / f"{Path(pdf_name).stem}.png"
            shutil.copyfile(image.file_path, target)
            return


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: uv run python test/pypupdf_pic.py <PDF 文件或目录>")
        return 2
    target = Path(sys.argv[1])
    pdf_paths = _collect_pdfs(target)
    if not pdf_paths:
        print(f"未找到 PDF 文件（{target}）")
        return 1

    service = ResumeParserService()
    photo_count = 0
    for pdf_path in pdf_paths:
        try:
            resume = service.parse_pdf(pdf_path.read_bytes(), pdf_path.name)
            if resume.candidate_photo_id:
                photo_count += 1
                _dump_photo(resume, pdf_path.name)
        except Exception as exc:  # noqa: BLE001
            # 详细报错已由 ResumeParserService 写入日志文件
            print(f"[{pdf_path.name}] 解析失败: {exc}")

    print(f"共 {len(pdf_paths)} 份简历，其中 {photo_count} 份识别出照片")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
