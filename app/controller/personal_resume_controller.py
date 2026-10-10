"""Owner-checked resume file routes for public personal mode."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.core.dependencies import get_resume_parser_service
from app.core.exceptions import ResumeFileNotFoundError
from app.model.resume import Resume
from app.service.resume_parser_service import ResumeParserService


router = APIRouter(prefix="/resumes", tags=["personal-resumes"])


def _owned_resume(request: Request, resume_id: str, service: ResumeParserService) -> Resume:
    resume = service.get_resume(resume_id)
    if not resume or resume.owner_id != request.state.user.id:
        raise HTTPException(status_code=404, detail="简历不存在")
    return resume


@router.get("/{resume_id}/pdf")
def pdf(request: Request, resume_id: str,
        service: ResumeParserService = Depends(get_resume_parser_service)) -> Response:
    _owned_resume(request, resume_id, service)
    try:
        content = service.read_pdf(resume_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历不存在") from exc
    return Response(content=content, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/{resume_id}/images/{image_id}")
def image(request: Request, resume_id: str, image_id: str,
          service: ResumeParserService = Depends(get_resume_parser_service)) -> Response:
    _owned_resume(request, resume_id, service)
    try:
        content = service.read_image(resume_id, image_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历不存在") from exc
    return Response(content=content, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{resume_id}/download")
def download(request: Request, resume_id: str,
             service: ResumeParserService = Depends(get_resume_parser_service)) -> Response:
    resume = _owned_resume(request, resume_id, service)
    try:
        content = service.read_pdf(resume_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历不存在") from exc
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(resume.file_name)}",
        "Cache-Control": "no-store",
    })
