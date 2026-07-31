from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from .config import Settings
from .downloader import DownloadError, FileTooLargeError, download_media, get_title
from .health import start_health_server
from .storage import LimitReachedError, UsageStats, UsageStorage, UserAccess
from .urls import canonical_url, extract_youtube_id

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start", "help"))
async def start(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
        return
    if not await _service_available(message, message.from_user, settings, storage):
        return
    await message.answer(
        "Пришли ссылку на YouTube-видео. Я предложу скачать видео или MP3.\n\n"
        "Скачивай только материалы, на которые у тебя есть права."
    )


@router.message(Command("whoami"))
async def whoami(message: Message) -> None:
    if message.from_user is None:
        return
    username = f"@{message.from_user.username}" if message.from_user.username else "не установлен"
    await message.answer(
        f"Твой Telegram user ID: <code>{message.from_user.id}</code>\nUsername: {username}",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def stats(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_user_ids:
        await message.answer("Эта команда доступна только администратору.")
        return
    days = _stats_days(message.text or "")
    report = storage.stats(days)
    await message.answer(_format_stats(report, days))


@router.message(Command("quota"))
async def quota(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
        return
    if message.from_user is None:
        return
    if message.from_user.id in settings.admin_user_ids:
        await message.answer("Тариф: администратор\nЛимит: без ограничений")
        return
    access = _user_access(message.from_user.id, settings, storage)
    await message.answer(
        f"Тариф: {access.plan}\n"
        f"Использовано сегодня: {access.used_today} из {access.daily_limit}\n"
        f"Осталось: {access.remaining}"
    )


@router.message(Command("maintenance"))
async def maintenance(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not _is_admin(message.from_user, settings):
        await message.answer("Эта команда доступна только администратору.")
        return
    argument = _command_argument(message.text or "")
    if argument not in {"on", "off"}:
        state = "включён" if storage.maintenance_enabled() else "выключен"
        await message.answer(f"Режим обслуживания сейчас {state}.\n/maintenance on|off")
        return
    enabled = argument == "on"
    storage.set_maintenance(enabled)
    await message.answer(
        "Режим обслуживания включён. Новые загрузки приостановлены."
        if enabled
        else "Режим обслуживания выключен. Бот снова принимает загрузки."
    )


@router.message(Command("plan"))
async def plan(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not _is_admin(message.from_user, settings):
        await message.answer("Эта команда доступна только администратору.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in {"free", "premium"}:
        await message.answer("Формат: /plan USER_ID free|premium")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return
    if storage.set_plan(user_id, parts[2]):
        await message.answer(f"Пользователю {user_id} назначен тариф {parts[2]}.")
    else:
        await message.answer("Пользователь ещё не запускал бота.")


@router.message(Command("block", "unblock"))
async def block(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not _is_admin(message.from_user, settings):
        await message.answer("Эта команда доступна только администратору.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: /block USER_ID или /unblock USER_ID")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return
    blocked = parts[0].split("@", 1)[0] == "/block"
    if storage.set_blocked(user_id, blocked):
        action = "заблокирован" if blocked else "разблокирован"
        await message.answer(f"Пользователь {user_id} {action}.")
    else:
        await message.answer("Пользователь ещё не запускал бота.")


@router.message(F.text)
async def accept_url(
    message: Message,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
        return
    if not await _service_available(message, message.from_user, settings, storage):
        return
    video_id = extract_youtube_id(message.text or "")
    if not video_id:
        await message.answer(
            "Не удалось распознать ссылку. Поддерживаются обычные YouTube-ссылки, "
            "youtu.be, Shorts и Live."
        )
        return

    url = canonical_url(video_id)
    status = await message.answer("Проверяю видео…")
    try:
        title = await get_title(url)
    except DownloadError as exc:
        logger.warning("Could not inspect %s: %s", video_id, exc)
        await status.edit_text("Не удалось получить информацию о видео.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Видео", callback_data=f"download:video:{video_id}"),
                InlineKeyboardButton(text="🎵 MP3", callback_data=f"download:audio:{video_id}"),
            ]
        ]
    )
    await status.edit_text(f"Что скачать?\n\n{title}", reply_markup=keyboard)


@router.callback_query(F.data.startswith("download:"))
async def handle_download(
    callback: CallbackQuery,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not await _register_user(callback.message, callback.from_user, settings, storage):
        return
    if not await _service_available(
        callback.message,
        callback.from_user,
        settings,
        storage,
    ):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"video", "audio"}:
        await callback.message.answer("Некорректная команда загрузки.")
        return

    kind, video_id = parts[1], parts[2]
    if extract_youtube_id(canonical_url(video_id)) != video_id:
        await callback.message.answer("Некорректный идентификатор видео.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    status = await callback.message.answer(
        "Загружаю и подготавливаю файл. Это может занять несколько минут…"
    )
    media = None
    started_at = perf_counter()
    daily_limit = None
    if callback.from_user.id not in settings.admin_user_ids:
        daily_limit = _user_access(callback.from_user.id, settings, storage).daily_limit
    try:
        event_id = storage.start_download(
            callback.from_user.id,
            callback.from_user.username,
            video_id,
            kind,
            daily_limit=daily_limit,
        )
    except LimitReachedError:
        await status.edit_text("Дневной лимит исчерпан. Посмотреть остаток можно командой /quota.")
        return
    try:
        media = await download_media(
            canonical_url(video_id),
            kind=kind,
            max_bytes=settings.max_upload_bytes,
            timeout_seconds=settings.download_timeout_seconds,
        )
        document = FSInputFile(media.path, filename=media.path.name)
        if kind == "audio":
            await callback.message.answer_audio(document, title=media.title)
        else:
            await callback.message.answer_video(
                document, caption=media.title, supports_streaming=True
            )
        storage.finish_download(
            event_id,
            "success",
            bytes_sent=media.path.stat().st_size,
            duration_ms=_elapsed_ms(started_at),
        )
        await status.delete()
    except FileTooLargeError:
        storage.finish_download(
            event_id,
            "too_large",
            duration_ms=_elapsed_ms(started_at),
            error_code="too_large",
        )
        await status.edit_text(
            "Файл не помещается в лимит Telegram. Попробуй скачать MP3 "
            "или выбери более короткое видео."
        )
    except DownloadError as exc:
        storage.finish_download(
            event_id,
            "download_error",
            duration_ms=_elapsed_ms(started_at),
            error_code=type(exc).__name__,
        )
        logger.exception("Download failed for %s: %s", video_id, exc)
        await status.edit_text(
            "Не удалось скачать видео. YouTube мог временно ограничить запрос "
            "или для ролика требуется авторизация."
        )
    except Exception as exc:
        storage.finish_download(
            event_id,
            "internal_error",
            duration_ms=_elapsed_ms(started_at),
            error_code=type(exc).__name__,
        )
        logger.exception("Unexpected failure for %s", video_id)
        await status.edit_text("Произошла внутренняя ошибка. Попробуй немного позже.")
    finally:
        if media is not None:
            media.cleanup()


async def run(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = Bot(token=settings.bot_token)
    storage = UsageStorage(settings.database_path)
    storage.initialize()
    health_runner = await start_health_server(
        storage,
        host=settings.health_host,
        port=settings.health_port,
    )
    await _configure_command_menu(bot, settings)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot, settings=settings, storage=storage)
    finally:
        await health_runner.cleanup()
        await bot.session.close()


def main() -> None:
    asyncio.run(run(Settings.from_env()))


async def _configure_command_menu(bot: Bot, settings: Settings) -> None:
    public_commands = [
        BotCommand(command="start", description="Как пользоваться ботом"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="quota", description="Мой тариф и остаток лимита"),
        BotCommand(command="whoami", description="Показать мой Telegram ID"),
    ]
    await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())
    for admin_id in settings.admin_user_ids:
        await bot.set_my_commands(
            [
                *public_commands,
                BotCommand(command="stats", description="Закрытая статистика"),
                BotCommand(command="maintenance", description="Режим обслуживания"),
            ],
            scope=BotCommandScopeChat(chat_id=admin_id),
        )


async def _register_user(
    message: Message,
    user: User | None,
    settings: Settings,
    storage: UsageStorage,
) -> bool:
    if user is None:
        return False
    if settings.require_username and not user.username:
        await message.answer(
            "Для использования бота установи публичный @username в настройках "
            "Telegram и попробуй снова."
        )
        return False
    storage.upsert_user(
        user.id,
        user.username,
        user.full_name,
    )
    return True


async def _service_available(
    message: Message,
    user: User | None,
    settings: Settings,
    storage: UsageStorage,
) -> bool:
    if user is None:
        return False
    if user.id in settings.admin_user_ids:
        return True
    if storage.maintenance_enabled():
        await message.answer(
            "Сейчас ведутся технические работы. Уже запущенные задачи завершаются, "
            "а новые загрузки скоро снова станут доступны."
        )
        return False
    access = _user_access(user.id, settings, storage)
    if access.is_blocked:
        await message.answer("Доступ к сервису для этого аккаунта ограничен.")
        return False
    if access.remaining <= 0:
        await message.answer(
            "Дневной лимит исчерпан. Новые операции станут доступны после 00:00 UTC."
        )
        return False
    return True


def _user_access(
    user_id: int,
    settings: Settings,
    storage: UsageStorage,
) -> UserAccess:
    return storage.user_access(
        user_id,
        free_limit=settings.free_daily_limit,
        premium_limit=settings.premium_daily_limit,
    )


def _is_admin(user: User | None, settings: Settings) -> bool:
    return bool(user and user.id in settings.admin_user_ids)


def _command_argument(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip().lower() if len(parts) == 2 else ""


def _stats_days(text: str) -> int:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return 7
    value = parts[1].lower().removesuffix("d").strip()
    try:
        days = int(value)
    except ValueError:
        return 7
    return min(max(days, 1), 365)


def _elapsed_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


def _format_stats(stats: UsageStats, days: int) -> str:
    top = "\n".join(
        f"{index}. {_user_label(username)}: {downloads}"
        for index, (username, downloads) in enumerate(stats.top_users, start=1)
    )
    if not top:
        top = "пока нет"
    return (
        f"Статистика за {days} дн.\n\n"
        f"Пользователей: {stats.users}\n"
        f"Запросов: {stats.downloads}\n"
        f"Успешно: {stats.successful}\n"
        f"Ошибок: {stats.failed}\n"
        f"MP3 / видео: {stats.audio} / {stats.video}\n"
        f"Передано: {_human_bytes(stats.bytes_sent)}\n\n"
        f"Топ пользователей:\n{top}"
    )


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def _user_label(username: str) -> str:
    if username.startswith("id:"):
        return username
    return f"@{username}"
