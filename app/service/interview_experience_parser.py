"""Deterministic parsing of numbered, plain-text interview notes."""

import re
import unicodedata
from datetime import datetime
from uuid import uuid4

import pymupdf

from app.model.interview_experience import CATEGORY_LABELS


QUESTION_RE = re.compile(r"^(?:Q\s*)?(\d+(?:\.\d+)*)(?:[、:：，,.．)）]\s*|\s+)(.+)$", re.I)
CATEGORY_RE = re.compile(r"^#?\s*(项目问题|八股问题|算法题|其他|反问)(?:\s*[（(]\s*(\d+)\s*min\s*[)）])?\s*[:：]?$", re.I)
ANSWER_RE = re.compile(r"^(现场回答|复盘答案|面试官回答)\s*[:：]\s*(.*)$")
LABEL_TO_CATEGORY = {label: key for key, label in CATEGORY_LABELS.items()}
ANSWER_FIELDS = {"现场回答": "on_site_answer", "复盘答案": "review_answer",
                 "面试官回答": "interviewer_answer"}
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
MARKDOWN_LIST_RE = re.compile(r"^(\s*)(?:[-*+]\s+|\d+[.)、]\s+)(.+)$")
MARKDOWN_NUMBER_RE = re.compile(r"^(\s*)(\d+(?:\.\d+)+)(?:[.)、]\s*|\s+)(.+)$")
MINUTES_RE = re.compile(r"(?:约|至少|不到)?\s*(\d+)\s*(?:min|分钟)", re.I)
SECTION_CATEGORIES = (
    ("反问", "reverse"), ("八股", "fundamentals"),
    ("算法", "algorithm"), ("手撕", "algorithm"),
    ("项目", "project"),
)


def parse_experience_text(source: str) -> dict:
    """Parse visible numbering and adjacent answers without semantic guesses."""
    if not isinstance(source, str) or len(source) > 100000:
        raise ValueError("原文不能超过 100000 字")
    if re.search(r"(?m)^#{1,6}\s+.+", source) and re.search(r"(?m)^\s*(?:[-*+]\s+|\d+\.\s+)\S", source):
        return parse_experience_markdown(source)
    questions: list[dict] = []
    unrecognized: list[dict] = []
    warnings: list[str] = []
    category_minutes: dict[str, int] = {}
    numbers: dict[str, str] = {}
    category = "project"
    current: dict | None = None
    active_answer: str | None = None
    feeling: list[str] = []
    in_feeling = False
    title: str | None = None
    company: str | None = None
    position: str | None = None
    interviewed_at: str | None = None

    for line_no, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("面试感受：") or line.startswith("面试感受:"):
            in_feeling = True
            current = None
            feeling.append(line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip())
            continue
        metadata = re.match(r"^(公司|岗位|面试时间)\s*[:：]\s*(.+)$", line)
        if metadata:
            field, value = metadata.groups()
            if field == "公司":
                company = value[:200]
            elif field == "岗位":
                position = value[:200]
            else:
                try:
                    interviewed_at = datetime.fromisoformat(value.replace("/", "-")).isoformat(timespec="minutes")
                except ValueError:
                    warnings.append(f"第 {line_no} 行：面试时间格式无法识别，请手动填写")
                    unrecognized.append({"line": line_no, "text": line})
            current = None
            active_answer = None
            continue
        category_match = CATEGORY_RE.match(line)
        if category_match:
            category = LABEL_TO_CATEGORY[category_match.group(1)]
            if category_match.group(2):
                category_minutes[category] = int(category_match.group(2))
            current = None
            active_answer = None
            in_feeling = False
            continue
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
            current = None
            continue
        question_match = QUESTION_RE.match(line)
        if question_match:
            in_feeling = False
            number, question_text = question_match.groups()
            question_category = category
            if question_text.startswith("反问：") or question_text.startswith("反问:"):
                question_category = "reverse"
                question_text = re.sub(r"^反问\s*[:：]\s*", "", question_text)
            parent_number = number.rsplit(".", 1)[0] if "." in number else None
            parent_id = numbers.get(parent_number) if parent_number else None
            if parent_number and not parent_id:
                warnings.append(f"第 {line_no} 行：找不到 {number} 的父问题 {parent_number}，请在预览中修正")
            item_id = str(uuid4())
            current = {
                "id": item_id, "number": number, "parent_question_id": parent_id,
                "category": question_category, "question_text": question_text.strip(),
                "on_site_answer": None, "review_answer": None,
                "interviewer_answer": None, "source_line": line_no,
                "needs_parent_review": bool(parent_number and not parent_id),
            }
            questions.append(current)
            numbers[number] = item_id
            active_answer = None
            continue
        answer_match = ANSWER_RE.match(line)
        if current and answer_match:
            active_answer = ANSWER_FIELDS[answer_match.group(1)]
            current[active_answer] = answer_match.group(2).strip() or None
            continue
        if in_feeling:
            feeling.append(line)
            continue
        if current:
            if current["category"] == "reverse" and active_answer is None:
                warnings.append(f"第 {line_no} 行：反问后的回答归属不明，请手动选择")
                unrecognized.append({"line": line_no, "text": line})
                continue
            field = active_answer or "on_site_answer"
            current[field] = "\n".join(filter(None, [current[field], line]))
        else:
            unrecognized.append({"line": line_no, "text": line})
    if len(questions) > 500:
        raise ValueError("一次最多解析 500 道问题")
    return {"title": title, "company": company, "position": position,
            "interviewed_at": interviewed_at, "questions": questions,
            "feeling": "\n".join(feeling).strip(),
            "category_minutes": category_minutes, "unrecognized": unrecognized,
            "warnings": warnings}


def _heading_category(value: str) -> str | None:
    for keyword, category in SECTION_CATEGORIES:
        if keyword in value:
            return category
    return None


def parse_experience_markdown(source: str) -> dict:
    """Parse Markdown headings and lists into editable question hierarchy."""
    if not isinstance(source, str) or len(source) > 100000:
        raise ValueError("原文不能超过 100000 字")
    questions: list[dict] = []
    unrecognized: list[dict] = []
    warnings: list[str] = []
    category_minutes: dict[str, int] = {}
    feeling: list[str] = []
    title = None
    category = "other"
    section = ""
    topic_stack: dict[int, dict] = {}
    bullet_stack: list[tuple[int, dict]] = []
    source_numbers: dict[str, dict] = {}
    child_counts: dict[str | None, int] = {}
    current: dict | None = None
    in_code = False

    def add_question(value: str, parent: dict | None, line_no: int) -> dict:
        parent_id = parent["id"] if parent else None
        child_counts[parent_id] = child_counts.get(parent_id, 0) + 1
        number = (parent["number"] + "." if parent else "") + str(child_counts[parent_id])
        item = {
            "id": str(uuid4()), "number": number,
            "parent_question_id": parent_id, "category": category,
            "question_text": value[:2000].strip(), "on_site_answer": None,
            "review_answer": None, "interviewer_answer": None,
            "source_line": line_no, "needs_parent_review": False,
        }
        questions.append(item)
        return item

    for line_no, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_code = not in_code
            unrecognized.append({"line": line_no, "text": line})
            continue
        if in_code:
            unrecognized.append({"line": line_no, "text": line})
            continue
        if not line or re.fullmatch(r"[-*_]{3,}", line):
            continue
        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            depth, value = len(heading.group(1)), heading.group(2).strip()
            if title is None and depth == 1 and _heading_category(value) is None:
                title = value[:200]
                continue
            if "面试时长" in value:
                section = "duration"
                current = None
                continue
            if "面试感受" in value or "整体感受" in value:
                section = "feeling"
                current = None
                continue
            inferred = _heading_category(value)
            if inferred and (depth == 1 or (depth == 2 and category != "project")):
                category = inferred
                section = "questions"
                topic_stack.clear()
                bullet_stack.clear()
                source_numbers.clear()
                current = None
                minutes = MINUTES_RE.search(value)
                if minutes:
                    category_minutes[category] = int(minutes.group(1))
                # A project name at a nested level is also a useful parent topic.
                if depth == 2 and inferred == "project":
                    current = add_question(value, None, line_no)
                    topic_stack[depth] = current
                continue
            section = "questions"
            bullet_stack.clear()
            for level in list(topic_stack):
                if level >= depth:
                    del topic_stack[level]
            parent = topic_stack[max(topic_stack)] if topic_stack else None
            current = add_question(value, parent, line_no)
            topic_stack[depth] = current
            continue
        if line.startswith(("整体感受：", "整体感受:", "面试感受：", "面试感受:")):
            feeling.append(re.split(r"[:：]", line, maxsplit=1)[1].strip())
            current = None
            continue
        if section == "feeling":
            feeling.append(line)
            continue
        numbered = MARKDOWN_NUMBER_RE.match(raw)
        list_match = MARKDOWN_LIST_RE.match(raw)
        if section == "duration":
            if list_match:
                value = list_match.group(2)
                inferred = _heading_category(value)
                minutes = MINUTES_RE.search(value)
                if inferred and minutes:
                    category_minutes[inferred] = int(minutes.group(1))
            elif line.startswith("约 ") or MINUTES_RE.fullmatch(line):
                pass
            else:
                unrecognized.append({"line": line_no, "text": line})
            continue
        if list_match or numbered:
            indent = len((numbered or list_match).group(1).expandtabs(4))
            value = (numbered.group(3) if numbered else list_match.group(2)).strip()
            if value.startswith(("（", "(", "我回答", "回答：", "回答:")) and current:
                field = "interviewer_answer" if category == "reverse" else "on_site_answer"
                current[field] = "\n".join(filter(None, (current[field], value)))
                continue
            while bullet_stack and bullet_stack[-1][0] >= indent:
                bullet_stack.pop()
            parent = bullet_stack[-1][1] if bullet_stack else (topic_stack[max(topic_stack)] if topic_stack else None)
            if numbered:
                source_number = numbered.group(2)
                parent_number = source_number.rsplit(".", 1)[0]
                parent = source_numbers.get(parent_number, parent)
                if parent_number not in source_numbers:
                    warnings.append(f"第 {line_no} 行：未找到 {source_number} 对应的父问题，请核对层级")
            current = add_question(value, parent, line_no)
            bullet_stack.append((indent, current))
            if numbered:
                source_numbers[source_number] = current
            else:
                simple_number = re.match(r"\s*(\d+)[.)、]\s+", raw)
                if simple_number:
                    source_numbers[simple_number.group(1)] = current
            continue
        if raw[:1].isspace() and current:
            field = "interviewer_answer" if category == "reverse" else "on_site_answer"
            current[field] = "\n".join(filter(None, (current[field], line)))
            continue
        if line.startswith(("现场回答：", "复盘答案：", "面试官回答：")) and current:
            label, answer = line.split("：", 1)
            current[ANSWER_FIELDS[label]] = answer.strip() or None
            continue
        unrecognized.append({"line": line_no, "text": line})
        current = None
    if len(questions) > 500:
        raise ValueError("一次最多解析 500 道问题")
    if unrecognized:
        warnings.append("部分说明或非列表内容未自动归入问题，请在预览中核对原文")
    return {"title": title, "company": None, "position": None,
            "interviewed_at": None, "questions": questions,
            "feeling": "\n".join(feeling).strip(),
            "category_minutes": category_minutes, "unrecognized": unrecognized,
            "warnings": warnings}


def extract_experience_pdf(content: bytes) -> str:
    """Extract a text-layer PDF as Markdown-like headings and questions."""
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF 文件无法打开") from exc
    try:
        if len(document) > 30:
            raise ValueError("PDF 最多支持 30 页")
        lines: list[str] = []
        try:
            for page in document:
                for block in page.get_text("dict", sort=True)["blocks"]:
                    if "lines" not in block:
                        continue
                    spans = [span for row in block["lines"] for span in row["spans"]]
                    value = " ".join("".join(span["text"] for span in row["spans"]).strip()
                                     for row in block["lines"]).strip()
                    if not value:
                        continue
                    size = max(span["size"] for span in spans)
                    prefix = "# " if size >= 18 else "## " if size >= 16 else ""
                    lines.append(prefix + unicodedata.normalize("NFKC", value))
        except Exception as exc:
            raise ValueError("PDF 文字提取失败") from exc
        result = "\n".join(lines)
        if len(result) < 20:
            raise ValueError("PDF 没有可提取的文字，当前暂不支持扫描件")
        if len(result) > 100000:
            raise ValueError("提取文字不能超过 100000 字")
        return result
    finally:
        document.close()
