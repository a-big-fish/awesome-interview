"""Generate a synthetic, paginated export fixture for Android UI screenshots."""

from pathlib import Path

from app.model.interview_experience import InterviewExperience, InterviewQuestion
from app.service.interview_experience_export import export_pdf


def main() -> None:
    experience = InterviewExperience(
        owner_id="acceptance-fixture",
        title="示例公司 · 后端开发一面",
        company="示例公司",
        position="后端开发",
        total_minutes=60,
        feeling="讨论围绕项目设计、缓存与并发控制展开。",
        category_minutes={"project": 30, "fundamentals": 20, "reverse": 10},
    )
    rows = []
    for index in range(1, 24):
        category = "project" if index < 12 else "fundamentals" if index < 21 else "reverse"
        question = InterviewQuestion(
            experience_id=experience.id,
            category=category,
            asked_order=index,
            question_text=f"示例问题 {index}：请描述方案、边界条件和取舍。",
            on_site_answer="现场回答示例：先说明思路，再讨论异常处理。" if category != "reverse" else None,
            review_answer="复盘答案示例：补充性能、可观测性和回退方案。" if category != "reverse" else None,
            interviewer_answer="面试官回答示例：团队采用分阶段交付。" if category == "reverse" else None,
        )
        rows.append({"question": question, "number": f"Q{index}", "depth": 0,
                     "parent_number": None})
    target = Path(__file__).resolve().parents[1] / "app/src/debug/assets/acceptance-export.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(export_pdf(experience, rows))
    print(target)


if __name__ == "__main__":
    main()
