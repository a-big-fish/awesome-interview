from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.model.meeting_entry import MeetingEntry
from app.shared.invitation_parser import InvitationParser


class MeetingParserService(InvitationParser):
    """Adapt shared invitation facts to the enterprise meeting record."""

    def parse(self, dto: MeetingEntryCreateDTO) -> MeetingEntry:
        facts = self.parse_facts(dto.raw_text)
        candidate_name = (
            dto.candidate_name
            or facts.candidate_name_hint
            or facts.subject
            or "未填写候选人"
        )
        subject = facts.subject or (
            f"{candidate_name}的面试" if facts.kind_hint == "interview" else "未命名会议"
        )
        return MeetingEntry(
            candidate_name=candidate_name,
            position=facts.position_hint or dto.position,
            subject=subject,
            kind=facts.kind_hint,
            start_time=facts.start_time,
            end_time=facts.end_time,
            platform=facts.platform,
            room_number=facts.room_number,
            meeting_url=facts.meeting_url,
            interviewer_names=dto.interviewer_names,
            source=dto.source,
            source_id=dto.source_id,
            candidate_external_id=dto.candidate_external_id,
            note=dto.note,
            raw_text=dto.raw_text,
            resume_id=dto.resume_id,
        )
