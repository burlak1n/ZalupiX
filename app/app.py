import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from schemas import (
    HealthResponse,
    ScheduleResponse,
    UserProfileUpdateRequest,
    UserProfileResponse,
)
from service.scheduler_service import SchedulerService
from service.user_service import UserService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем сервис
scheduler_service = SchedulerService()
user_service = UserService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan менеджер для FastAPI"""
    logger.info("🚀 FastAPI приложение запускается...")
    yield
    logger.info("🛑 FastAPI приложение завершает работу...")


def create_app() -> FastAPI:
    """Создание и настройка FastAPI приложения"""
    app = FastAPI(
        title="Google Sheets Events API",
        description="API для работы с событиями из Google Sheets",
        version="1.0.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # Улучшенная настройка CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
    )

    return app


# Создаем приложение
app = create_app()


# Dependency для получения сервиса
def get_scheduler_service() -> SchedulerService:
    """Dependency для получения сервиса планировщика"""
    return scheduler_service

def get_user_service() -> UserService:
    """Dependency для получения сервиса пользователя"""
    return user_service


# Удаляем устаревший on_event, используем lifespan


@app.get("/health")
async def health_check(
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
) -> HealthResponse:
    """Проверка состояния API"""
    try:
        logger.info("Выполняется health check")
        if scheduler_service.is_connected():
            logger.info("Google API подключен")
            return HealthResponse(status="healthy", google_api="connected")
        else:
            logger.warning("Google API отключен")
            return HealthResponse(status="healthy", google_api="disconnected")
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/schedule")
async def get_schedule(
    refresh: bool = Query(
        default=False, description="Принудительное обновление кэша", examples=[False]
    ),
    start_date: date = Query(
        default=None, description="Начальная дата", examples=[None]
    ),
    end_date: date = Query(
        default=None, description="Конечная дата", examples=[None]
    ),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    """Получение расписания событий"""
    try:
        if refresh:
            logger.info("Принудительное обновление расписания")
            events = await scheduler_service.refresh_events()
            logger.info(f"Обновлено {len(events)} событий")
            return ScheduleResponse(events=events)
        else:
            logger.info("Запрос расписания")
            events = await scheduler_service.get_events(start_date, end_date)
            return ScheduleResponse(events=events)
    except Exception as e:
        logger.error(f"Failed to get schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@app.post("/schedule/add")
async def add_schedule(
    schedule: ScheduleResponse,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    """Добавление события в расписание TODO"""
    # TODO: добавить валидацию данных
    logger.info(f"Добавление события в расписание: {schedule}")

    scheduler_service.add_event(schedule.events)
    return ScheduleResponse(events=[])


@app.get("/user/{telegram_id}")
async def get_user_profile(
    telegram_id: int,
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Получение профиля пользователя TODO"""
    # TODO: доделать получение профиля пользователя
    return UserProfileResponse(
        user_profile=user_service.get_user_profile(telegram_id)
    )


@app.post("/user/update")
async def update_user_profile(
    update_request: UserProfileUpdateRequest,
    user_service: UserService = Depends(get_user_service),
) -> bool:
    """Обновление профиля пользователя с указанием полей для изменения TODO"""
    logger.info(f"Обновление профиля пользователя: {update_request}")
    # TODO: реализовать обновление профиля через user_service
    return user_service.update_user_profile(update_request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
