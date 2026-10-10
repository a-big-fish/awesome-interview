"""Interview experience lifecycle, ordering, export, and account isolation."""

import re
import json
from uuid import uuid4

import pymupdf
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import (
    get_interview_experience_mapper, get_my_resume_mapper, get_personal_event_mapper,
)
from app.main import create_app
from app.mapper.memory_auth_mapper import MemoryAuthMapper
from app.mapper.memory_interview_experience_mapper import MemoryInterviewExperienceMapper
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.model.auth import AuthUser
from app.model.interview_experience import InterviewExperience, InterviewQuestion
from app.service.auth_service import AuthService, hash_password
from app.service.interview_experience_export import export_pdf


def _csrf(page) -> str:
    found = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert found
    return found.group(1)


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/auth/login", data={
        "csrf_token": _csrf(client.get("/auth/login")),
        "identifier": email, "password": password,
    }, follow_redirects=False)
    assert response.status_code == 303
    return _csrf(client.get("/my-schedule/experiences"))


def _fixture():
    settings = Settings(
        _env_file=None, app_mode="public_personal", storage_backend="postgres",
        public_base_url="https://testserver", email_verification_required=False,
    )
    auth_mapper = MemoryAuthMapper()
    app = create_app(settings, AuthService(auth_mapper, settings))
    experience_mapper = MemoryInterviewExperienceMapper()
    events = MemoryPersonalEventMapper()
    app.dependency_overrides[get_interview_experience_mapper] = lambda: experience_mapper
    app.dependency_overrides[get_personal_event_mapper] = lambda: events
    app.dependency_overrides[get_my_resume_mapper] = lambda: MemoryMyResumeMapper()
    return app, auth_mapper, experience_mapper, events


def test_experience_tree_answers_exports_and_detached_event():
    app, auth_mapper, experience_mapper, events = _fixture()
    user = AuthUser(email="notes@example.com", password_hash=hash_password("notes-strong-password"),
                    email_verified=True)
    auth_mapper.create_user(user)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, user.email, "notes-strong-password")
        created_event = client.post("/my-schedule/events", data={
            "csrf_token": csrf, "source": "manual", "title": "后端一面",
            "event_type": "interview", "start_at": "2026-10-08T10:00",
            "end_at": "2026-10-08T11:00", "timezone": "Asia/Shanghai",
        }, follow_redirects=False)
        assert created_event.status_code == 303
        event = events.list_all(user.id)[0]
        assert "还没有问题记录" in client.get(f"/my-schedule/interviews/{event.id}").text
        created = client.post("/my-schedule/experiences", data={
            "csrf_token": csrf, "title": "后端一面", "linked_event_id": event.id,
            "company": "示例公司", "position": "后端开发",
        }, follow_redirects=False)
        assert created.status_code == 303
        experience = experience_mapper.list_experiences(user.id)[0]
        assert event.id in created.headers["location"]

        def add(text: str, category: str, parent: str = "") -> None:
            result = client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
                "csrf_token": csrf, "question_text": text, "category": category,
                "parent_question_id": parent,
            }, follow_redirects=False)
            assert result.status_code == 303

        add("介绍项目", "project")
        first = experience_mapper.list_questions(experience.id, user.id)[0]
        add("Java 是什么", "fundamentals")
        add("项目如何部署", "project", first.id)
        followup = experience_mapper.list_questions(experience.id, user.id)[2]
        add("遇到的故障如何恢复", "project", followup.id)
        page = client.get(f"/my-schedule/interviews/{event.id}")
        assert page.status_code == 200
        assert "Q1.1.1" in page.text
        assert page.text.index("介绍项目") < page.text.index("Java 是什么") < page.text.index("项目如何部署")
        category_page = client.get(f"/my-schedule/experiences/{experience.id}?category=project")
        assert "项目如何部署" in category_page.text
        assert "Java 是什么" not in category_page.text
        second = experience_mapper.list_questions(experience.id, user.id)[1]
        moved = client.post(
            f"/my-schedule/experiences/{experience.id}/questions/{second.id}/move",
            data={"csrf_token": csrf, "direction": "up"}, follow_redirects=False,
        )
        assert moved.status_code == 303
        reordered = client.get(f"/my-schedule/experiences/{experience.id}?category=project")
        assert "Q2.1.1" in reordered.text
        chronological = client.get(f"/my-schedule/experiences/{experience.id}?category=all")
        assert chronological.text.index("介绍项目") < chronological.text.index("Java 是什么")

        edited = client.post(
            f"/my-schedule/experiences/{experience.id}/questions/{followup.id}/edit", data={
                "csrf_token": csrf, "question_text": "项目如何部署", "category": "project",
                "on_site_answer": "使用容器", "review_answer": "补充灰度与回滚",
            }, follow_redirects=False,
        )
        assert edited.status_code == 303
        assert "现场回答" in client.get(f"/my-schedule/interviews/{event.id}").text
        preview = client.get(f"/my-schedule/experiences/{experience.id}/export")
        assert preview.status_code == 200
        assert "简洁线条" in preview.text
        assert "项目如何部署" in preview.text
        assert "导出预览" in preview.text
        flat_preview = client.get(f"/my-schedule/experiences/{experience.id}/export?style=flat")
        assert flat_preview.status_code == 200
        assert "export-paper-flat" in flat_preview.text
        assert flat_preview.text.index("介绍项目") < flat_preview.text.index("Java 是什么")
        assert client.get(f"/my-schedule/experiences/{experience.id}/export?style=unknown").status_code == 422
        md = client.get(f"/my-schedule/experiences/{experience.id}/export.md")
        assert md.status_code == 200
        assert md.headers["content-disposition"] == f'attachment; filename="interview-experience-{experience.id}.md"'
        assert md.headers["content-type"].startswith("text/markdown")
        assert "现场回答：使用容器" in md.text
        assert "复盘答案：补充灰度与回滚" in md.text
        assert "完整提问顺序" not in md.text
        assert "完整提问顺序" not in preview.text
        customized = client.get(
            f"/my-schedule/experiences/{experience.id}/export",
            params={"title": "公开版面经", "hide_company": "true", "hide_position": "true",
                    "hide_interviewed_at": "true"},
        )
        assert customized.status_code == 200
        assert "<h2>公开版面经</h2>" in customized.text
        assert "公司：示例公司" not in customized.text
        assert "岗位：后端开发" not in customized.text
        customized_md = client.get(
            f"/my-schedule/experiences/{experience.id}/export.md",
            params={"title": "公开版面经", "hide_company": "true", "hide_position": "true",
                    "hide_interviewed_at": "true"},
        )
        assert customized_md.text.startswith("# 公开版面经\n")
        assert "示例公司" not in customized_md.text
        assert "后端开发" not in customized_md.text
        assert "面试时间" not in customized_md.text
        assert experience_mapper.list_experiences(user.id)[0].title == "后端一面"
        hide_site = client.get(f"/my-schedule/experiences/{experience.id}/export",
                               params={"hide_on_site_answer": "true"})
        assert "现场回答</b>使用容器" not in hide_site.text
        assert "复盘答案</b>补充灰度与回滚" in hide_site.text
        hide_review_md = client.get(f"/my-schedule/experiences/{experience.id}/export.md",
                                    params={"hide_review_answer": "true"})
        assert "现场回答：使用容器" in hide_review_md.text
        assert "复盘答案：补充灰度与回滚" not in hide_review_md.text
        all_hidden = {"hide_on_site_answer": "true", "hide_review_answer": "true",
                      "hide_interviewer_answer": "true", "hide_interviewed_at": "true"}
        all_hidden_preview = client.get(f"/my-schedule/experiences/{experience.id}/export",
                                        params=all_hidden)
        assert "面试时间：2026" not in all_hidden_preview.text
        assert "现场回答</b>使用容器" not in all_hidden_preview.text
        assert "复盘答案</b>补充灰度与回滚" not in all_hidden_preview.text
        assert "显示所有回答和面试时间" in all_hidden_preview.text
        all_hidden_md = client.get(f"/my-schedule/experiences/{experience.id}/export.md",
                                   params=all_hidden)
        assert "面试时间" not in all_hidden_md.text
        assert "现场回答：使用容器" not in all_hidden_md.text
        assert "复盘答案：补充灰度与回滚" not in all_hidden_md.text
        flat_md = client.get(f"/my-schedule/experiences/{experience.id}/export.md?style=flat")
        assert flat_md.status_code == 200
        assert "完整提问顺序" not in flat_md.text
        assert "1. **介绍项目**" in flat_md.text
        assert flat_md.text.index("介绍项目") < flat_md.text.index("Java 是什么")
        pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-disposition"] == f'attachment; filename="interview-experience-{experience.id}.pdf"'
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")
        inline_pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf?style=lines&inline=true")
        assert inline_pdf.status_code == 200
        assert inline_pdf.headers["content-disposition"].startswith("inline;")
        assert inline_pdf.content.startswith(b"%PDF")
        text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf.content, filetype="pdf"))
        assert "项目如何部署" in text
        assert "补充灰度与回滚" in text
        assert "完整提问顺序" not in text
        customized_pdf = client.get(
            f"/my-schedule/experiences/{experience.id}/export.pdf",
            params={"title": "公开版面经", "hide_company": "true", "hide_position": "true",
                    "hide_interviewed_at": "true"},
        )
        customized_text = "\n".join(page.get_text() for page in pymupdf.open(stream=customized_pdf.content, filetype="pdf"))
        assert "公开版面经" in customized_text
        assert "示例公司" not in customized_text
        assert "后端开发" not in customized_text
        all_hidden_pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf",
                                    params=all_hidden)
        all_hidden_text = "\n".join(page.get_text() for page in pymupdf.open(stream=all_hidden_pdf.content, filetype="pdf"))
        assert "面试时间" not in all_hidden_text
        assert "使用容器" not in all_hidden_text
        assert "补充灰度与回滚" not in all_hidden_text
        flat_pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf?style=flat")
        assert flat_pdf.status_code == 200
        flat_text = "\n".join(page.get_text() for page in pymupdf.open(stream=flat_pdf.content, filetype="pdf"))
        assert "项目如何部署" in flat_text
        assert "完整提问顺序" not in flat_text

        deleted_event = client.post(f"/my-schedule/events/{event.id}/delete",
                                    data={"csrf_token": csrf}, follow_redirects=False)
        assert deleted_event.status_code == 303
        independent = client.get(f"/my-schedule/experiences/{experience.id}")
        assert independent.status_code == 200
        assert "关联的面试日程已不存在" in independent.text
        assert "2026-10-08" in independent.text

        deleted_question = client.post(
            f"/my-schedule/experiences/{experience.id}/questions/{first.id}/delete",
            data={"csrf_token": csrf}, follow_redirects=False)
        assert deleted_question.status_code == 303
        assert len(experience_mapper.list_questions(experience.id, user.id)) == 1
        deleted_experience = client.post(f"/my-schedule/experiences/{experience.id}/delete",
                                         data={"csrf_token": csrf}, follow_redirects=False)
        assert deleted_experience.status_code == 303
        assert client.get(f"/my-schedule/experiences/{experience.id}").status_code == 404


def test_experience_owner_scope_and_event_link_validation():
    app, auth_mapper, mapper, events = _fixture()
    alice = AuthUser(email="alice.notes@example.com", password_hash=hash_password("alice-notes-password"),
                     email_verified=True)
    bob = AuthUser(email="bob.notes@example.com", password_hash=hash_password("bob-notes-password"),
                   email_verified=True)
    auth_mapper.create_user(alice)
    auth_mapper.create_user(bob)
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        alice_csrf = _login(alice_client, alice.email, "alice-notes-password")
        bob_csrf = _login(bob_client, bob.email, "bob-notes-password")
        created = alice_client.post("/my-schedule/experiences", data={
            "csrf_token": alice_csrf, "title": "只属于 Alice 的面经",
        }, follow_redirects=False)
        assert created.status_code == 303
        experience = mapper.list_experiences(alice.id)[0]
        question = alice_client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": alice_csrf, "question_text": "隐私问题", "category": "other",
        }, follow_redirects=False)
        assert question.status_code == 303
        question_id = mapper.list_questions(experience.id, alice.id)[0].id
        assert "只属于 Alice" not in bob_client.get("/my-schedule/experiences").text
        for path in (f"/my-schedule/experiences/{experience.id}",
                     f"/my-schedule/experiences/{experience.id}/export",
                     f"/my-schedule/experiences/{experience.id}/export.md",
                     f"/my-schedule/experiences/{experience.id}/export.pdf"):
            assert bob_client.get(path).status_code == 404
        assert bob_client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": bob_csrf, "question_text": "越权", "category": "other",
        }).status_code == 404
        assert bob_client.post(
            f"/my-schedule/experiences/{experience.id}/questions/{question_id}/edit", data={
                "csrf_token": bob_csrf, "question_text": "越权", "category": "other",
            }).status_code == 404
        assert bob_client.post(f"/my-schedule/experiences/{experience.id}/delete",
                               data={"csrf_token": bob_csrf}).status_code == 404
        assert bob_client.post("/my-schedule/experiences", data={
            "csrf_token": bob_csrf, "title": "错误关联", "linked_event_id": "unknown",
        }).status_code == 422
        assert len(mapper.list_experiences(alice.id)) == 1


def test_pdf_export_wraps_long_chinese_answers_across_pages():
    experience = InterviewExperience(owner_id="test", title="长文本面经")
    question = InterviewQuestion(
        experience_id=experience.id, category="project", asked_order=1,
        question_text="介绍设计方案", review_answer="这是一次完整复盘。" * 900 + "最后的结论。",
    )
    pdf = export_pdf(experience, [{
        "question": question, "number": "Q1", "depth": 0, "parent_number": None,
    }])
    document = pymupdf.open(stream=pdf, filetype="pdf")
    assert len(document) > 1
    assert "最后的结论" in "".join(page.get_text() for page in document)
    assert all(page.rect.height == 842 for page in document)


def test_reverse_questions_and_optional_section_minutes_export_consistently():
    app, auth_mapper, mapper, _ = _fixture()
    user = AuthUser(email="reverse@example.com", password_hash=hash_password("reverse-strong-password"),
                    email_verified=True)
    auth_mapper.create_user(user)
    experience = mapper.save_experience(InterviewExperience(owner_id=user.id, title="二面复盘"))
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, user.email, "reverse-strong-password")
        url = f"/my-schedule/experiences/{experience.id}/draft"
        questions = [
            {"id": str(uuid4()), "category": "project", "question_text": "介绍项目", "sibling_order": 1},
            {"id": str(uuid4()), "category": "reverse", "question_text": "团队规模？",
             "interviewer_answer": "十人团队", "review_answer": "不能保存的复盘", "sibling_order": 2},
        ]
        payload = {"version": experience.updated_at.isoformat(), "questions": questions,
                   "category_minutes": {"project": 10, "reverse": 5}, "total_minutes": None}
        saved = client.post(url, data={"csrf_token": csrf, "payload": json.dumps(payload)})
        assert saved.status_code == 200
        stored = mapper.find_experience(experience.id, user.id)
        assert stored.category_minutes == {"project": 10, "reverse": 5}
        assert stored.total_minutes is None
        reverse = mapper.list_questions(experience.id, user.id)[1]
        assert reverse.interviewer_answer == "十人团队"
        assert reverse.review_answer is None
        preview = client.get(f"/my-schedule/experiences/{experience.id}/export")
        assert "总耗时（15 min）" in preview.text
        assert "项目问题（10 min）" in preview.text
        assert "反问（5 min）" in preview.text
        assert "面试官回答</b>十人团队" in preview.text
        assert "复盘答案</b>不能保存的复盘" not in preview.text
        md = client.get(f"/my-schedule/experiences/{experience.id}/export.md")
        assert "## 反问（5 min）" in md.text
        assert "面试官回答：十人团队" in md.text
        flat = client.get(f"/my-schedule/experiences/{experience.id}/export.md?style=flat")
        assert "模块用时：项目问题（10 min）、反问（5 min）" in flat.text
        pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf")
        pdf_text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf.content, filetype="pdf"))
        assert "总耗时（15 min）" in pdf_text
        assert "反问（5 min）" in pdf_text
        assert "十人团队" in pdf_text
        hidden = client.get(f"/my-schedule/experiences/{experience.id}/export.md",
                            params={"hide_interviewer_answer": "true"})
        assert "十人团队" not in hidden.text
        invalid = dict(payload, version=saved.json()["version"], category_minutes={"project": -1})
        assert client.post(url, data={"csrf_token": csrf, "payload": json.dumps(invalid)}).status_code == 422
        assert mapper.find_experience(experience.id, user.id).category_minutes == {"project": 10, "reverse": 5}
        payload["version"] = saved.json()["version"]
        payload["total_minutes"] = 30
        updated = client.post(url, data={"csrf_token": csrf, "payload": json.dumps(payload)})
        assert updated.status_code == 200
        assert mapper.find_experience(experience.id, user.id).total_minutes == 30
        assert "总耗时（30 min）" in client.get(f"/my-schedule/experiences/{experience.id}/export").text
        legacy_payload = {"version": updated.json()["version"], "questions": questions}
        assert client.post(url, data={"csrf_token": csrf, "payload": json.dumps(legacy_payload)}).status_code == 200
        assert mapper.find_experience(experience.id, user.id).total_minutes == 30


def test_draft_batch_save_is_atomic_and_rejects_stale_or_cross_account_updates():
    app, auth_mapper, mapper, _ = _fixture()
    alice = AuthUser(email="draft.alice@example.com", password_hash=hash_password("alice-draft-password"),
                     email_verified=True)
    bob = AuthUser(email="draft.bob@example.com", password_hash=hash_password("bob-draft-password"),
                   email_verified=True)
    auth_mapper.create_user(alice)
    auth_mapper.create_user(bob)
    experience = mapper.save_experience(InterviewExperience(owner_id=alice.id, title="草稿测试"))
    root_id, child_id = str(uuid4()), str(uuid4())
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        alice_csrf = _login(alice_client, alice.email, "alice-draft-password")
        bob_csrf = _login(bob_client, bob.email, "bob-draft-password")
        url = f"/my-schedule/experiences/{experience.id}/draft"

        def post(client, csrf, version, questions):
            return client.post(url, data={"csrf_token": csrf, "payload": json.dumps({
                "version": version, "questions": questions,
            })})

        draft = [
            {"id": root_id, "category": "project", "question_text": "介绍项目",
             "sibling_order": 1},
            {"id": child_id, "parent_question_id": root_id, "category": "project",
             "question_text": "如何部署", "review_answer": "灰度发布", "sibling_order": 1},
        ]
        version = experience.updated_at.isoformat()
        assert post(bob_client, bob_csrf, version, draft).status_code == 404
        assert mapper.list_questions(experience.id, alice.id) == []
        invalid = [dict(draft[0]), dict(draft[1], parent_question_id="missing")]
        assert post(alice_client, alice_csrf, version, invalid).status_code == 422
        assert mapper.list_questions(experience.id, alice.id) == []
        saved = post(alice_client, alice_csrf, version, draft)
        assert saved.status_code == 200
        assert len(mapper.list_questions(experience.id, alice.id)) == 2
        assert post(alice_client, alice_csrf, version, []).status_code == 409
        assert len(mapper.list_questions(experience.id, alice.id)) == 2
        removed = post(alice_client, alice_csrf, saved.json()["version"], [draft[0]])
        assert removed.status_code == 200
        assert [item.id for item in mapper.list_questions(experience.id, alice.id)] == [root_id]


def test_feeling_draft_and_export_and_list_counts():
    app, auth_mapper, mapper, _ = _fixture()
    user = AuthUser(email="feelings@example.com", password_hash=hash_password("feelings-password"),
                    email_verified=True)
    auth_mapper.create_user(user)
    experience = mapper.save_experience(InterviewExperience(owner_id=user.id, title="二面记录"))
    mapper.save_question(InterviewQuestion(experience_id=experience.id, category="project",
                                           asked_order=1, question_text="项目难点？"), user.id)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, user.email, "feelings-password")
        listing = client.get("/my-schedule/experiences")
        assert "experience;dur=" in listing.headers["server-timing"]
        assert mapper.count_questions_by_experience(user.id)[experience.id] == 1
        saved = client.post(f"/my-schedule/experiences/{experience.id}/draft", data={
            "csrf_token": csrf,
            "payload": json.dumps({"version": experience.updated_at.isoformat(),
                                   "questions": [item.model_dump(mode="json") for item in
                                                 mapper.list_questions(experience.id, user.id)],
                                   "feeling": "整体交流顺畅，项目追问较多。"}),
        })
        assert saved.status_code == 200
        assert mapper.find_experience(experience.id, user.id).feeling == "整体交流顺畅，项目追问较多。"
        detail = client.get(f"/my-schedule/experiences/{experience.id}")
        assert "面试感受" in detail.text
        preview = client.get(f"/my-schedule/experiences/{experience.id}/export")
        assert preview.text.index("整体交流顺畅") < preview.text.index("项目难点？")
        markdown = client.get(f"/my-schedule/experiences/{experience.id}/export.md")
        assert markdown.text.index("## 面试感受") < markdown.text.index("项目难点？")
        pdf = client.get(f"/my-schedule/experiences/{experience.id}/export.pdf")
        pdf_text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf.content, filetype="pdf"))
        assert "整体交流顺畅" in pdf_text
