from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app.controller.schema.common import ApiResponseVO
from app.controller.schema.resume_vo import ResumeVO
from app.core.dependencies import get_resume_parser_service
from app.core.exceptions import ResumeFileNotFoundError, ResumeParseError
from app.service.resume_parser_service import ResumeParserService

router = APIRouter(tags=["resumes"])


@router.post("/api/v1/resumes/parse", response_model=ApiResponseVO[ResumeVO])
async def parse_resume(
    resume: UploadFile,
    service: ResumeParserService = Depends(get_resume_parser_service),
) -> ApiResponseVO[ResumeVO]:
    try:
        parsed = await service.parse_upload(resume)
    except ResumeParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponseVO[ResumeVO](data=ResumeVO.from_domain(parsed))


@router.get("/api/v1/resumes/{resume_id}", response_model=ApiResponseVO[ResumeVO])
def get_resume(
    resume_id: str,
    service: ResumeParserService = Depends(get_resume_parser_service),
) -> ApiResponseVO[ResumeVO]:
    resume = service.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在或服务已重启")
    return ApiResponseVO[ResumeVO](data=ResumeVO.from_domain(resume))


@router.get("/resumes/{resume_id}/pdf")
def get_resume_pdf(
    resume_id: str,
    service: ResumeParserService = Depends(get_resume_parser_service),
) -> Response:
    """Serve the resume PDF for inline display inside an <iframe>."""
    try:
        content = service.read_pdf(resume_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历文件不存在") from exc
    return Response(content=content, media_type="application/pdf")


@router.get("/resumes/{resume_id}/images/{image_id}")
def get_resume_image(
    resume_id: str,
    image_id: str,
    service: ResumeParserService = Depends(get_resume_parser_service),
) -> Response:
    """Serve an image extracted from the resume PDF."""
    try:
        content = service.read_image(resume_id, image_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历图片不存在") from exc
    return Response(content=content, media_type="image/png")


@router.get("/resumes/{resume_id}/download")
def download_resume(
    resume_id: str,
    service: ResumeParserService = Depends(get_resume_parser_service),
) -> Response:
    """Download the resume PDF as an attachment."""
    try:
        content = service.read_pdf(resume_id)
    except ResumeFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="简历文件不存在") from exc
    resume = service.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历文件不存在")
    quoted_name = quote(resume.file_name)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}"
        },
    )
