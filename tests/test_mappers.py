from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.model.meeting_entry import MeetingEntry
from app.model.resume import Resume


def test_schedule_mapper_save_find_and_delete():
    mapper = MemoryScheduleMapper()
    entry = MeetingEntry(
        candidate_name="张三",
        subject="后端面试",
        start_time="2026-09-03T10:00:00+08:00",
        end_time="2026-09-03T10:30:00+08:00",
    )

    assert mapper.save(entry).id == entry.id
    assert mapper.find_by_date("2026-09-03")[0].id == entry.id
    assert mapper.find_by_id(entry.id).candidate_name == "张三"
    assert mapper.delete(entry.id) is True
    assert mapper.find_by_id(entry.id) is None


def test_resume_mapper_save_and_find():
    mapper = MemoryResumeMapper()
    resume = Resume(file_name="resume.pdf", pdf_path="data/resumes/resume.pdf")

    mapper.save(resume)
    assert mapper.find_by_id(resume.id).file_name == "resume.pdf"
