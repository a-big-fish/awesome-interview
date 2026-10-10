"""Portable Markdown and PDF exports for one personal interview experience."""

import pymupdf

from app.model.interview_experience import CATEGORY_LABELS, InterviewExperience

EXPORT_STYLES = {"lines", "flat"}


def effective_total_minutes(experience: InterviewExperience) -> int | None:
    """Use the entered total, or the optional module sum when no total was entered."""
    if experience.total_minutes is not None:
        return experience.total_minutes
    return sum(experience.category_minutes.values()) if experience.category_minutes else None


def section_heading(label: str, experience: InterviewExperience) -> str:
    category = next(key for key, name in CATEGORY_LABELS.items() if name == label)
    minutes = experience.category_minutes.get(category)
    return f"{label}（{minutes} min）" if minutes is not None else label


def _category_rows(rows: list[dict], category: str) -> list[dict]:
    by_id = {row["question"].id: row for row in rows}

    def path(row: dict) -> tuple[int, ...]:
        item = row["question"]
        parent = by_id.get(item.parent_question_id)
        order = item.sibling_order or item.asked_order
        return (*path(parent), order) if parent else (order,)

    return sorted((row for row in rows if row["question"].category == category),
                  key=path)


def export_sections(rows: list[dict], style: str) -> list[tuple[str | None, list[dict]]]:
    """Build the ordered sections shared by preview, Markdown, and PDF."""
    if style not in EXPORT_STYLES:
        raise ValueError("导出样式无效")
    if style == "flat":
        return [(None, sorted(rows, key=lambda row: row["question"].asked_order))]
    return [(label, group) for category, label in CATEGORY_LABELS.items()
            if (group := _category_rows(rows, category))]


def export_markdown(experience: InterviewExperience, rows: list[dict],
                    style: str = "lines", *, hide_on_site_answer: bool = False,
                    hide_review_answer: bool = False,
                    hide_interviewer_answer: bool = False) -> str:
    """Export an editable UTF-8 document in the selected layout."""
    lines = [f"# {experience.title}", ""]
    if experience.feeling:
        lines.extend(["## 面试感受", "", experience.feeling, ""])
    total = effective_total_minutes(experience)
    if total is not None:
        lines.extend([f"总耗时（{total} min）", ""])
    for label, value in (("公司", experience.company), ("岗位", experience.position),
                         ("面试时间", experience.interviewed_at)):
        if value:
            lines.append(f"- {label}：{value}")
    if len(lines) > 2:
        lines.append("")
    if style == "flat" and experience.category_minutes:
        lines.extend(["- 模块用时：" + "、".join(
            section_heading(label, experience) for key, label in CATEGORY_LABELS.items()
            if key in experience.category_minutes), ""])
    for category_label, group in export_sections(rows, style):
        if category_label:
            lines.extend([f"## {section_heading(category_label, experience)}", ""])
        for row in group:
            question = row["question"]
            indent = "  " * row["depth"] if style == "lines" else ""
            number = row["number"] if style == "lines" else f"{question.asked_order}."
            parent = f"（追问 {row['parent_number']}）" if style == "flat" and row["parent_number"] else ""
            heading = (f"{indent}- **{number} {question.question_text}**" if style == "lines"
                       else f"{number} **{question.question_text}{parent}**")
            answer_indent = f"{indent}  " if style == "lines" else "   "
            lines.extend([heading, ""])
            if question.category != "reverse" and question.on_site_answer and not hide_on_site_answer:
                lines.extend([f"{answer_indent}- 现场回答：{question.on_site_answer}", ""])
            if question.category != "reverse" and question.review_answer and not hide_review_answer:
                lines.extend([f"{answer_indent}- 复盘答案：{question.review_answer}", ""])
            if question.category == "reverse" and question.interviewer_answer and not hide_interviewer_answer:
                lines.extend([f"{answer_indent}- 面试官回答：{question.interviewer_answer}", ""])
    return "\n".join(lines).rstrip() + "\n"


def export_pdf(experience: InterviewExperience, rows: list[dict],
               style: str = "lines", *, hide_on_site_answer: bool = False,
               hide_review_answer: bool = False,
               hide_interviewer_answer: bool = False) -> bytes:
    """Render a paginated Chinese PDF with PyMuPDF's built-in CJK font."""
    sections = export_sections(rows, style)
    document = pymupdf.open()
    cjk_font = pymupdf.Font("china-s")
    latin_font = pymupdf.Font("helv")
    page = document.new_page(width=595, height=842)
    y = 56.0
    margin = 48.0
    ink = (0.10, 0.16, 0.27)
    muted = (0.43, 0.49, 0.59)
    accent = (0.18, 0.36, 0.83)

    def write_line(content: str, *, size: float = 11, gap: float = 18,
                   indent: float = 0, color: tuple[float, float, float] = ink) -> None:
        nonlocal page, y
        if y + gap > page.rect.height - margin:
            page = document.new_page(width=595, height=842)
            y = 56.0
        x = margin + indent
        run = ""
        run_is_cjk = False
        for char in content:
            is_cjk = ord(char) > 127
            if run and is_cjk != run_is_cjk:
                font = cjk_font if run_is_cjk else latin_font
                page.insert_text((x, y), run, fontname="china-s" if run_is_cjk else "helv",
                                 fontsize=size, color=color)
                x += font.text_length(run, fontsize=size)
                run = ""
            run += char
            run_is_cjk = is_cjk
        if run:
            page.insert_text((x, y), run, fontname="china-s" if run_is_cjk else "helv",
                             fontsize=size, color=color)
        y += gap

    def paragraph(content: str, *, size: float = 11, indent: float = 0,
                  color: tuple[float, float, float] = ink, gap: float = 18) -> None:
        nonlocal y
        width = page.rect.width - 2 * margin - indent
        for raw_line in content.splitlines() or [""]:
            remaining = raw_line
            if not remaining:
                y += gap * .65
                continue
            while remaining:
                take, used_width = 0, 0.0
                for char in remaining:
                    font = cjk_font if ord(char) > 127 else latin_font
                    char_width = font.text_length(char, fontsize=size)
                    if take and used_width + char_width > width:
                        break
                    used_width += char_width
                    take += 1
                write_line(remaining[:take], size=size, gap=gap, indent=indent, color=color)
                remaining = remaining[take:]

    def section_gap(amount: float = 12) -> None:
        nonlocal y
        y += amount

    paragraph(experience.title, size=20, gap=29)
    section_gap(4)
    if experience.feeling:
        paragraph("面试感受", size=14, gap=23, color=accent)
        paragraph(experience.feeling, size=11, gap=18)
        section_gap(12)
    total = effective_total_minutes(experience)
    if total is not None:
        paragraph(f"总耗时（{total} min）", size=11, gap=18, color=muted)
    for label, value in (("公司", experience.company), ("岗位", experience.position),
                         ("面试时间", experience.interviewed_at)):
        if value:
            paragraph(f"{label}：{value}", size=10, gap=16, color=muted)
    section_gap(16)
    if style == "flat" and experience.category_minutes:
        paragraph("模块用时：" + "、".join(
            section_heading(label, experience) for key, label in CATEGORY_LABELS.items()
            if key in experience.category_minutes), size=10, gap=18, color=muted)
        section_gap(8)
    for category_label, group in sections:
        if category_label:
            paragraph(section_heading(category_label, experience), size=14, gap=23, color=accent)
            page.draw_line((margin, y - 10), (page.rect.width - margin, y - 10),
                           color=(0.85, 0.89, 0.96), width=.7)
            section_gap(4)
        for row in group:
            question = row["question"]
            indent = min(row["depth"], 5) * 16 if style == "lines" else 0
            number = row["number"] if style == "lines" else f"{question.asked_order}."
            parent = f"  （追问 {row['parent_number']}）" if style == "flat" and row["parent_number"] else ""
            start_page, start_y = page, y
            paragraph(f"{number}  {question.question_text}{parent}", indent=indent + (15 if style == "lines" else 0))
            if style == "lines" and page is start_page:
                x = margin + indent + 4
                page.draw_line((x, start_y - 12), (x, y - 12), color=(0.58, 0.69, 0.90), width=.8)
                page.draw_line((x, start_y - 5), (x + 8, start_y - 5), color=(0.58, 0.69, 0.90), width=.8)
            if question.category != "reverse" and question.on_site_answer and not hide_on_site_answer:
                paragraph(f"现场回答：{question.on_site_answer}", size=10,
                          indent=indent + (16 if style == "lines" else 24), color=muted, gap=16)
            if question.category != "reverse" and question.review_answer and not hide_review_answer:
                paragraph(f"复盘答案：{question.review_answer}", size=10,
                          indent=indent + (16 if style == "lines" else 24), color=muted, gap=16)
            if question.category == "reverse" and question.interviewer_answer and not hide_interviewer_answer:
                paragraph(f"面试官回答：{question.interviewer_answer}", size=10,
                          indent=indent + (16 if style == "lines" else 24), color=muted, gap=16)
            section_gap(8 if style == "lines" else 12)
        section_gap(10)
    data = document.tobytes(garbage=4, deflate=True)
    document.close()
    return data
