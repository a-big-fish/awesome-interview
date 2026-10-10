from app.shared.invitation_parser import InvitationParser


def test_shared_parser_returns_meeting_facts_without_candidate_model():
    facts = InvitationParser().parse_facts(
        "会议时间：2026/10/02 10:00-10:30\n"
        "会议主题：项目讨论\n"
        "https://meeting.tencent.com/dm/project"
    )
    assert facts.kind_hint == "meeting"
    assert facts.subject == "项目讨论"
    assert facts.candidate_name_hint is None
    assert facts.platform == "腾讯会议"
    assert facts.start_time.isoformat() == "2026-10-02T10:00:00+08:00"
