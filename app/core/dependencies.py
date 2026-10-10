from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper
from app.mapper.base_enterprise_calendar_mapper import BaseEnterpriseCalendarMapper
from app.mapper.base_personal_event_mapper import BasePersonalEventMapper
from app.mapper.base_personal_todo_mapper import BasePersonalTodoMapper
from app.mapper.base_resume_file_storage import ResumeFileStorage
from app.mapper.base_resume_mapper import BaseResumeMapper
from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.mapper.local_resume_file_storage import LocalResumeFileStorage
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_interview_experience_mapper import MemoryInterviewExperienceMapper
from app.mapper.memory_enterprise_calendar_mapper import MemoryEnterpriseCalendarMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.mapper.memory_personal_todo_mapper import MemoryPersonalTodoMapper
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.mapper.postgres_my_resume_mapper import PostgresMyResumeMapper
from app.mapper.postgres_interview_experience_mapper import PostgresInterviewExperienceMapper
from app.mapper.postgres_enterprise_calendar_mapper import PostgresEnterpriseCalendarMapper
from app.mapper.postgres_personal_event_mapper import PostgresPersonalEventMapper
from app.mapper.postgres_personal_todo_mapper import PostgresPersonalTodoMapper
from app.mapper.postgres_resume_mapper import PostgresResumeMapper
from app.mapper.postgres_schedule_mapper import PostgresScheduleMapper
from app.mapper.storage_factory import build_resume_file_storage
from app.service.ai_interview_service import AIInterviewService
from app.service.ai_providers.base import AIInterviewProvider
from app.service.ai_providers.openai_compatible import OpenAICompatibleProvider
from app.service.ai_providers.static import StaticAIInterviewProvider
from app.service.my_interview_service import MyInterviewService
from app.service.resume_parser_service import ResumeParserService
from app.service.schedule_service import ScheduleService
from app.service.enterprise_calendar_service import EnterpriseCalendarService
from app.service.personal_schedule_service import PersonalScheduleService
from app.service.personal_todo_service import PersonalTodoService
from app.service.interview_experience_service import InterviewExperienceService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _build_schedule_mapper(settings: Settings) -> BaseScheduleMapper:
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresScheduleMapper(settings=settings)
    return MemoryScheduleMapper()


def _build_resume_mapper(settings: Settings) -> BaseResumeMapper:
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresResumeMapper(settings=settings)
    return MemoryResumeMapper()


def _build_resume_file_storage(settings: Settings) -> ResumeFileStorage:
    if settings.storage_backend in {"rustfs", "minio", "postgres"}:
        return build_resume_file_storage(settings)
    return LocalResumeFileStorage(Path("data"))


@lru_cache
def get_schedule_mapper() -> BaseScheduleMapper:
    return _build_schedule_mapper(get_settings())


@lru_cache
def get_resume_mapper() -> BaseResumeMapper:
    return _build_resume_mapper(get_settings())


@lru_cache
def get_schedule_service() -> ScheduleService:
    return ScheduleService(
        schedule_mapper=get_schedule_mapper(),
        calendar_service=get_enterprise_calendar_service(),
    )


@lru_cache
def get_resume_file_storage() -> ResumeFileStorage:
    return _build_resume_file_storage(get_settings())


@lru_cache
def get_resume_parser_service() -> ResumeParserService:
    return ResumeParserService(
        resume_mapper=get_resume_mapper(),
        file_storage=get_resume_file_storage(),
    )


@lru_cache
def get_ai_interview_provider() -> AIInterviewProvider:
    settings = get_settings()
    if settings.ai_provider == "openai_compatible":
        return OpenAICompatibleProvider(settings)
    return StaticAIInterviewProvider()


@lru_cache
def get_ai_interview_service() -> AIInterviewService:
    return AIInterviewService(
        schedule_mapper=get_schedule_mapper(),
        resume_mapper=get_resume_mapper(),
        file_storage=get_resume_file_storage(),
        provider=get_ai_interview_provider(),
        settings=get_settings(),
    )

def _build_my_resume_mapper(settings: Settings) -> BaseMyResumeMapper:
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresMyResumeMapper(settings=settings)
    return MemoryMyResumeMapper()


@lru_cache
def get_my_resume_mapper() -> BaseMyResumeMapper:
    return _build_my_resume_mapper(get_settings())


@lru_cache
def get_my_interview_service() -> MyInterviewService:
    return MyInterviewService(
        schedule_mapper=get_schedule_mapper(),
        resume_mapper=get_resume_mapper(),
        profile_mapper=get_my_resume_mapper(),
    )


@lru_cache
def get_enterprise_calendar_mapper() -> BaseEnterpriseCalendarMapper:
    settings = get_settings()
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresEnterpriseCalendarMapper(settings=settings)
    return MemoryEnterpriseCalendarMapper()


@lru_cache
def get_enterprise_calendar_service() -> EnterpriseCalendarService:
    return EnterpriseCalendarService(get_enterprise_calendar_mapper())


@lru_cache
def get_personal_event_mapper() -> BasePersonalEventMapper:
    settings = get_settings()
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresPersonalEventMapper(settings=settings)
    return MemoryPersonalEventMapper()


def get_personal_schedule_service(
    request: Request,
    mapper: BasePersonalEventMapper = Depends(get_personal_event_mapper),
    profile_mapper: BaseMyResumeMapper = Depends(get_my_resume_mapper),
) -> PersonalScheduleService:
    owner_id = request.state.user.id if request.app.state.settings.app_mode == "public_personal" else "local"
    return PersonalScheduleService(mapper=mapper, profile_mapper=profile_mapper, owner_id=owner_id)


@lru_cache
def get_personal_todo_mapper() -> BasePersonalTodoMapper:
    settings = get_settings()
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresPersonalTodoMapper(settings=settings)
    return MemoryPersonalTodoMapper()


def get_personal_todo_service(
    request: Request,
    mapper: BasePersonalTodoMapper = Depends(get_personal_todo_mapper),
) -> PersonalTodoService:
    owner_id = request.state.user.id if request.app.state.settings.app_mode == "public_personal" else "local"
    return PersonalTodoService(mapper, owner_id)


@lru_cache
def get_interview_experience_mapper() -> BaseInterviewExperienceMapper:
    settings = get_settings()
    if settings.storage_backend in {"postgres", "rustfs", "minio"}:
        return PostgresInterviewExperienceMapper(settings=settings)
    return MemoryInterviewExperienceMapper()


def get_interview_experience_service(
    request: Request,
    mapper: BaseInterviewExperienceMapper = Depends(get_interview_experience_mapper),
    schedule_service: PersonalScheduleService = Depends(get_personal_schedule_service),
) -> InterviewExperienceService:
    owner_id = request.state.user.id if request.app.state.settings.app_mode == "public_personal" else "local"
    return InterviewExperienceService(mapper, schedule_service, owner_id)
