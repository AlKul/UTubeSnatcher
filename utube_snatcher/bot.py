from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .config import Settings
from .downloader import DownloadError, FileTooLargeError, download_media, get_title
from .urls import canonical_url, extract_youtube_id

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start", "help"))
async def start(message: Message) -> None:
    await message.answer(
        "Пришли ссылку на YouTube-видео. Я предложу скачать видео или MP3.\n\n"
        "Скачивай только материалы, на которые у тебя есть права."
    )


@router.message(F.text)
async def accept_url(message: Message) -> None:
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
async def handle_download(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
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
        await status.delete()
    except FileTooLargeError:
        await status.edit_text(
            "Файл не помещается в лимит Telegram. Попробуй скачать MP3 "
            "или выбери более короткое видео."
        )
    except DownloadError as exc:
        logger.exception("Download failed for %s: %s", video_id, exc)
        await status.edit_text(
            "Не удалось скачать видео. YouTube мог временно ограничить запрос "
            "или для ролика требуется авторизация."
        )
    finally:
        if media is not None:
            media.cleanup()


async def run(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot, settings=settings)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run(Settings.from_env()))
