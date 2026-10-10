"""Plain-text experience parsing and public plaza boundaries."""

import json

from fastapi.testclient import TestClient

from app.model.interview_experience import InterviewExperience
from app.service.interview_experience_parser import (
    extract_experience_pdf, parse_experience_markdown, parse_experience_text,
)
from tests.test_interview_experience import _fixture, _login
from app.model.auth import AuthUser
from app.service.auth_service import hash_password


def test_numbered_questions_answers_and_hierarchy():
    result = parse_experience_text("""# 后端一面
公司：示例公司
岗位：后端开发
面试时间：2026/10/08 14:00
项目问题（10 min）
1、介绍一下项目
使用 Spring Boot。
1.1 并发如何处理？
现场回答：使用限流。
复盘答案：补充幂等。
2：上线后遇到过故障吗？
3，反问：如何进行代码评审？
面试官回答：每周一次。
""")
    assert result["title"] == "后端一面"
    assert result["company"] == "示例公司"
    assert result["position"] == "后端开发"
    assert result["interviewed_at"] == "2026-10-08T14:00"
    assert result["category_minutes"] == {"project": 10}
    first, child, second, reverse = result["questions"]
    assert first["on_site_answer"] == "使用 Spring Boot。"
    assert child["parent_question_id"] == first["id"]
    assert child["on_site_answer"] == "使用限流。"
    assert child["review_answer"] == "补充幂等。"
    assert second["on_site_answer"] is None
    assert reverse["category"] == "reverse"
    assert reverse["interviewer_answer"] == "每周一次。"
    assert result["warnings"] == []


def test_missing_parent_and_ambiguous_reverse_answer_are_flagged():
    result = parse_experience_text("1.1 缺少父题\n2、反问：团队规模？\n约十人。")
    assert result["questions"][0]["needs_parent_review"]
    assert result["questions"][0]["parent_question_id"] is None
    assert len(result["warnings"]) == 2
    assert result["unrecognized"] == [{"line": 3, "text": "约十人。"}]


def test_markdown_headings_lists_and_notes_keep_context():
    result = parse_experience_text("""# 后端二面
## 面试时长
- 项目深挖：30 min
- 手撕代码：20 min
整体感受：讨论式交流。
# 项目深挖
## IM 项目
### Kafka
- 为什么引入 Kafka？
  我回答：用于解耦。
  - 消费失败怎么办？
# 八股
- 什么是事务隔离级别？
# 反问
- 团队如何协作？
""")
    assert result["title"] == "后端二面"
    assert result["category_minutes"] == {"project": 30, "algorithm": 20}
    assert result["feeling"] == "讨论式交流。"
    project, topic, question, followup, fundamentals, reverse = result["questions"]
    assert topic["parent_question_id"] == project["id"]
    assert question["parent_question_id"] == topic["id"]
    assert question["on_site_answer"] == "我回答：用于解耦。"
    assert followup["parent_question_id"] == question["id"]
    assert fundamentals["category"] == "fundamentals"
    assert reverse["category"] == "reverse"


def test_markdown_explicit_subquestion_number_keeps_parent():
    result = parse_experience_markdown("# 一面\n# 项目深挖\n1. 主问题\n1.1 追问")
    parent, child = result["questions"]
    assert child["parent_question_id"] == parent["id"]
    assert result["warnings"] == []


def test_markdown_numbered_list_can_be_reparsed_after_file_edit():
    result = parse_experience_text("# 一面\n# 项目深挖\n1. 介绍项目\n2. 如何优化？")
    assert [item["question_text"] for item in result["questions"]] == ["介绍项目", "如何优化？"]
    assert all(item["category"] == "project" for item in result["questions"])


def test_pdf_text_layer_is_extracted_and_scanned_pdf_rejected():
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Backend interview", fontsize=24)
    page.insert_text((72, 120), "1. What is caching?", fontsize=12)
    result = extract_experience_pdf(document.tobytes())
    assert "# Backend interview" in result
    assert "1. What is caching?" in result
    empty = pymupdf.open()
    empty.new_page()
    try:
        extract_experience_pdf(empty.tobytes())
        assert False, "image-only PDF should not parse as text"
    except ValueError as exc:
        assert "没有可提取的文字" in str(exc)


def test_markdown_file_preview_requires_owner_and_does_not_save_questions():
    app, auth_mapper, mapper, _ = _fixture()
    owner = AuthUser(email="file-owner@example.com", password_hash=hash_password("strong-password-1"),
                     email_verified=True)
    reader = AuthUser(email="file-reader@example.com", password_hash=hash_password("strong-password-2"),
                      email_verified=True)
    auth_mapper.create_user(owner)
    auth_mapper.create_user(reader)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, owner.email, "strong-password-1")
        client.post("/my-schedule/experiences", data={"csrf_token": csrf, "title": "待导入"})
        experience = mapper.list_experiences(owner.id)[0]
        write_page = client.get(f"/my-schedule/experiences/{experience.id}/write")
        import_page = client.get(f"/my-schedule/experiences/{experience.id}/import")
        assert write_page.status_code == import_page.status_code == 200
        assert 'data-editor-mode="write"' in write_page.text
        assert 'data-parser-file-preview' in write_page.text
        assert 'data-editor-mode-link="manual"' in write_page.text
        assert '5 问题' in write_page.text
        assert 'data-editor-mode="import"' in import_page.text
        assert 'data-parser-file-preview' in import_page.text
        response = client.post(f"/my-schedule/experiences/{experience.id}/parse-file",
                               data={"csrf_token": csrf},
                               files={"file": ("notes.md", b"# Interview\n# Project\n- Why cache?", "text/markdown")})
        assert response.status_code == 200
        assert any(item["question_text"] == "Why cache?" for item in response.json()["questions"])
        assert response.json()["source_text"].startswith("# Interview")
        assert mapper.list_questions(experience.id, owner.id) == []
        import pymupdf
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "Interview notes", fontsize=24)
        page.insert_text((72, 120), "1. Why cache?", fontsize=12)
        pdf_response = client.post(f"/my-schedule/experiences/{experience.id}/parse-file",
                                   data={"csrf_token": csrf},
                                   files={"file": ("notes.pdf", document.tobytes(), "application/pdf")})
        assert pdf_response.status_code == 200
        assert pdf_response.json()["questions"][0]["question_text"] == "Why cache?"
        client.post("/auth/logout", data={"csrf_token": csrf})
        reader_csrf = _login(client, reader.email, "strong-password-2")
        denied = client.post(f"/my-schedule/experiences/{experience.id}/parse-file",
                             data={"csrf_token": reader_csrf},
                             files={"file": ("notes.md", b"# Interview\n- Secret?", "text/markdown")})
        assert denied.status_code == 404
        assert client.get(f"/my-schedule/experiences/{experience.id}/write").status_code == 404
        assert client.get(f"/my-schedule/experiences/{experience.id}/import").status_code == 404


def test_plaza_requires_login_content_and_visibility():
    app, auth_mapper, mapper, _ = _fixture()
    owner = AuthUser(email="plaza-owner@example.com", password_hash=hash_password("strong-password-1"),
                     email_verified=True)
    reader = AuthUser(email="plaza-reader@example.com", password_hash=hash_password("strong-password-2"),
                      email_verified=True)
    auth_mapper.create_user(owner)
    auth_mapper.create_user(reader)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/my-schedule/experiences/plaza", follow_redirects=False).status_code == 303
        csrf = _login(client, owner.email, "strong-password-1")
        created = client.post("/my-schedule/experiences", data={"csrf_token": csrf, "title": "公开草稿"},
                              follow_redirects=False)
        assert created.status_code == 303
        experience = mapper.list_experiences(owner.id)[0]
        raw_saved = client.post(f"/my-schedule/experiences/{experience.id}/draft", data={
            "csrf_token": csrf, "payload": json.dumps({
                "version": experience.updated_at.isoformat(), "questions": [],
                "raw_text_draft": "1、尚未确认导入的问题"})})
        assert raw_saved.status_code == 200
        assert raw_saved.json()["raw_text_draft"] == "1、尚未确认导入的问题"
        parsed = client.post(f"/my-schedule/experiences/{experience.id}/parse", data={
            "csrf_token": csrf, "source": "1、介绍项目\nSpring Boot。\n1.1 如何处理并发？"})
        assert parsed.status_code == 200
        assert parsed.json()["questions"][1]["parent_question_id"] == parsed.json()["questions"][0]["id"]
        assert "公开草稿" not in client.get("/my-schedule/experiences/plaza").text
        add = client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": csrf, "question_text": "如何优化接口？", "category": "project",
            "on_site_answer": "先检查慢查询。"}, follow_redirects=False)
        assert add.status_code == 303
        assert "公开草稿" not in client.get("/my-schedule/experiences/plaza").text
        assert client.get(f"/my-schedule/experiences/plaza/{experience.id}").status_code == 404
        experience.company = "示例公司"
        mapper.save_experience(experience)
        plaza = client.get("/my-schedule/experiences/plaza")
        assert "公开草稿" in plaza.text
        assert "作者：热心用户_pla" in plaza.text
        assert 'href="/my-schedule/experiences/plaza" aria-current="page"' in plaza.text
        assert client.post("/my-schedule/profile", data={
            "csrf_token": csrf, "display_name": "面试笔记作者",
        }, follow_redirects=False).status_code == 303
        assert "作者：面试笔记作者" in client.get("/my-schedule/experiences/plaza").text
        client.post("/auth/logout", data={"csrf_token": csrf})
        reader_csrf = _login(client, reader.email, "strong-password-2")
        detail = client.get(f"/my-schedule/experiences/plaza/{experience.id}")
        assert "先检查慢查询。" in detail.text
        assert "作者：面试笔记作者" in detail.text
        assert owner.email not in detail.text
        assert client.get(f"/my-schedule/experiences/{experience.id}").status_code == 404
        assert client.post(f"/my-schedule/experiences/{experience.id}/parse", data={
            "csrf_token": reader_csrf, "source": "1、尝试读取私有草稿"}).status_code == 404
        assert client.post(f"/my-schedule/experiences/{experience.id}/visibility", data={
            "csrf_token": reader_csrf, "is_public": "private"}).status_code == 404
        client.post("/auth/logout", data={"csrf_token": reader_csrf})
        csrf = _login(client, owner.email, "strong-password-1")
        changed = client.post(f"/my-schedule/experiences/{experience.id}/visibility", data={
            "csrf_token": csrf, "is_public": "private"}, follow_redirects=False)
        assert changed.status_code == 303
        assert client.get(f"/my-schedule/experiences/plaza/{experience.id}").status_code == 404
        assert "公开草稿" not in client.get("/my-schedule/experiences/plaza").text


def test_historical_experience_defaults_public():
    assert InterviewExperience(owner_id="local", title="旧面经").is_public


def test_plaza_detail_keeps_question_tree_order():
    app, auth_mapper, mapper, _ = _fixture()
    owner = AuthUser(email="tree-owner@example.com", password_hash=hash_password("strong-password-1"),
                     email_verified=True)
    auth_mapper.create_user(owner)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, owner.email, "strong-password-1")
        client.post("/my-schedule/experiences", data={
            "csrf_token": csrf, "title": "树形顺序", "company": "示例公司",
        })
        experience = mapper.list_experiences(owner.id)[0]
        parent = client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": csrf, "question_text": "父问题", "category": "project",
        })
        assert parent.status_code == 200 or parent.status_code == 303
        child_parent = mapper.list_questions(experience.id, owner.id)[0]
        client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": csrf, "question_text": "另一主问题", "category": "project",
        })
        client.post(f"/my-schedule/experiences/{experience.id}/questions", data={
            "csrf_token": csrf, "question_text": "追问", "category": "project",
            "parent_question_id": child_parent.id,
        })
        html = client.get(f"/my-schedule/experiences/plaza/{experience.id}").text
        assert html.index("父问题") < html.index("追问") < html.index("另一主问题")


def test_editor_save_returns_to_list_and_explains_double_click():
    app, auth_mapper, mapper, _ = _fixture()
    owner = AuthUser(email="editor@example.com", password_hash=hash_password("strong-password-1"),
                     email_verified=True)
    auth_mapper.create_user(owner)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, owner.email, "strong-password-1")
        client.post("/my-schedule/experiences", data={
            "csrf_token": csrf, "title": "编辑测试", "company": "示例公司",
        })
        experience = mapper.list_experiences(owner.id)[0]
        editor = client.get(f"/my-schedule/experiences/{experience.id}")
        assert "双击即可编辑" in editor.text
        assert "保存面经并返回列表" in editor.text
        saved = client.post(f"/my-schedule/experiences/{experience.id}/edit", data={
            "csrf_token": csrf, "title": "编辑测试", "company": "示例公司",
            "is_public": "public",
        }, follow_redirects=False)
        assert saved.status_code == 303
        assert saved.headers["location"] == "/my-schedule/experiences"
