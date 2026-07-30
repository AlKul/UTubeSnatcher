from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from .config import Settings
from .downloader import DownloadError, FileTooLargeError, download_media, get_title
from .storage import UsageStats, UsageStorage
from .urls import canonical_url, extract_youtube_id

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start", "help"))
async def start(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
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


@router.message(F.text)
async def accept_url(
    message: Message,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
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
    event_id = storage.start_download(
        callback.from_user.id,
        callback.from_user.username,
        video_id,
        kind,
    )
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
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot, settings=settings, storage=storage)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run(Settings.from_env()))


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
