import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.config import CORS_ORIGINS
from app.container import Container
from app.repository.user import UserRepository
from app.schemas import (
    HealthResponse,
    ScheduleResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from app.service.models import UserProfile
from app.service.scheduler_service import SchedulerService
from app.service.user_service import UserService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем контейнер зависимостей
container = Container()
container.config.from_dict({})
container.wire(modules=[__name__])

# Создаем сервис
scheduler_service = SchedulerService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan менеджер для FastAPI"""
    logger.info("🚀 FastAPI приложение запускается...")
    yield
    logger.info("🛑 FastAPI приложение завершает работу...")
    # Закрываем движок БД
    if _engine:
        await _engine.dispose()


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
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
    )

    # Настройка dependency injection
    app.container = container

    return app


# Создаем приложение
app = create_app()


# Dependency для получения сервиса
def get_scheduler_service() -> SchedulerService:
    """Dependency для получения сервиса планировщика"""
    return scheduler_service


# Глобальные переменные для движка и фабрики сессий
_engine = None
_session_factory = None


def get_engine():
    """Получение движка БД (синглтон)"""
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        _engine = create_async_engine(
            "sqlite+aiosqlite:///./zalupix.db", echo=False, future=True
        )
    return _engine


def get_session_factory():
    """Получение фабрики сессий (синглтон)"""
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session():
    """Dependency для получения сессии БД"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_user_service(db_session=Depends(get_db_session)) -> UserService:
    """Dependency для получения сервиса пользователя"""
    repository = UserRepository(db_session)
    return UserService(repository)


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
    end_date: date = Query(default=None, description="Конечная дата", examples=[None]),
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
    user_profile = await user_service.get_user_profile(telegram_id)
    if user_profile is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return UserProfileResponse(user_profile=user_profile)


@app.post("/user/create")
async def create_user_profile(
    user_profile: UserProfile,
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Создание нового профиля пользователя"""
    logger.info(f"Создание профиля пользователя: {user_profile}")
    result = await user_service.create_user_profile(user_profile)
    return UserProfileResponse(user_profile=result)


@app.post("/user/update")
async def update_user_profile(
    update_request: UserProfileUpdateRequest,
    user_service: UserService = Depends(get_user_service),
) -> bool:
    """Обновление профиля пользователя с указанием полей для изменения"""
    logger.info(f"Обновление профиля пользователя: {update_request}")
    result = await user_service.update_user_profile(
        update_request.telegram_id, update_request
    )
    return result is not None


@app.post("/auth/telegram")
async def telegram_auth(request: Request) -> dict:
    """Аутентификация через Telegram Mini App"""
    try:
        data = await request.json()
        init_data = data.get("init_data")

        if not init_data:
            raise HTTPException(status_code=400, detail="init_data is required")

        # TODO: Добавить валидацию init_data с помощью BOT_TOKEN
        # Пока возвращаем успешный ответ
        logger.info("Telegram аутентификация успешна")
        return {"success": True, "message": "Telegram auth successful"}

    except Exception as e:
        logger.error(f"Telegram auth failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Telegram auth failed: {str(e)}")


@app.get("/auth/telegram/user")
async def get_telegram_user(request: Request) -> dict:
    """Получение данных пользователя Telegram"""
    try:
        # Получаем данные из заголовков или query параметров
        user_id = request.headers.get("X-Telegram-User-ID")

        if not user_id:
            raise HTTPException(status_code=400, detail="Telegram user ID is required")

        # TODO: Получить данные пользователя из базы данных
        logger.info(f"Получение данных пользователя Telegram: {user_id}")
        return {"user_id": user_id, "status": "authenticated"}

    except Exception as e:
        logger.error(f"Failed to get Telegram user: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get Telegram user: {str(e)}"
        )


if __name__ == "__main__":
    print("Запустите приложение командой: python run.py")
