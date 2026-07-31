from __future__ import annotations

import asyncio
import logging
import re
from time import perf_counter

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
from .downloader import (
    AuthenticationRequiredError,
    DownloadError,
    FileTooLargeError,
    GeoRestrictedError,
    MediaUnavailableError,
    RateLimitedError,
    download_media,
    get_title,
)
from .health import start_health_server
from .storage import LimitReachedError, UsageStats, UsageStorage, UserAccess
from .urls import parse_source_url

logger = logging.getLogger(__name__)
router = Router()
REPORT_REASONS = {
    "copyright": "Нарушение авторских прав",
    "personal": "Персональные данные",
    "prohibited": "Запрещённый контент",
    "owner": "Материал принадлежит мне",
    "other": "Другое",
}


class ClipForm(StatesGroup):
    waiting_for_range = State()


@router.message(Command("start", "help"))
async def start(message: Message, settings: Settings, storage: UsageStorage) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
        return
    if not await _service_available(message, message.from_user, settings, storage):
        return
    await message.answer(
        "Пришли публичную ссылку на YouTube, VK, TikTok или Instagram. "
        "Я предложу скачать видео или MP3."
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


@router.message(StateFilter(None), F.text)
async def accept_url(
    message: Message,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    if not await _register_user(message, message.from_user, settings, storage):
        return
    if not await _service_available(message, message.from_user, settings, storage):
        return
    source = parse_source_url(message.text or "")
    if not source:
        await message.answer(
            "Не удалось распознать ссылку. Поддерживаются публичные видео "
            "YouTube, VK, TikTok и Instagram Reels/posts."
        )
        return

    if storage.is_source_blocked(source.platform, source.media_id):
        await message.answer("Этот материал недоступен по результатам рассмотрения жалобы.")
        return

    status = await message.answer("Проверяю публикацию…")
    try:
        title = await get_title(source.url)
    except DownloadError as exc:
        logger.warning("Could not inspect %s:%s: %s", source.platform, source.media_id, exc)
        await status.edit_text(_download_error_message(exc, source.display_name))
        return

    request_id = storage.create_media_request(
        user_id=message.from_user.id,
        platform=source.platform,
        source_id=source.media_id,
        source_url=source.url,
        title=title,
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Видео",
                    callback_data=f"download:video:{request_id}",
                ),
                InlineKeyboardButton(
                    text="🎵 MP3",
                    callback_data=f"download:audio:{request_id}",
                ),
            ]
        ]
    )
    await status.edit_text(
        f"{source.display_name}\n\n{title}\n\nЧто скачать?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("clip:"))
async def request_clip(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not await _service_available(callback.message, callback.from_user, settings, storage):
        return
    try:
        request_id = int((callback.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.message.answer("Не удалось открыть редактор фрагмента.")
        return
    request = storage.media_request(request_id)
    if request is None or request.user_id != callback.from_user.id:
        await callback.message.answer("Исходная ссылка устарела. Пришли её ещё раз.")
        return
    await state.set_state(ClipForm.waiting_for_range)
    await state.update_data(request_id=request_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✕ Отмена", callback_data="clipcancel")]]
    )
    await callback.message.answer(
        "✂️ Укажи начало и конец фрагмента.\n\nНапример: <code>01:20–02:45</code>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "clipcancel")
async def cancel_clip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Отменено")
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Нарезка отменена.")


@router.message(ClipForm.waiting_for_range, F.text)
async def receive_clip_range(message: Message, state: FSMContext) -> None:
    clip_range = _parse_clip_range(message.text or "")
    if clip_range is None:
        await message.answer(
            "Не поняла таймкоды. Пришли их так: <code>01:20–02:45</code>",
            parse_mode="HTML",
        )
        return
    start, end = clip_range
    data = await state.get_data()
    request_id = int(data["request_id"])
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Создать видео",
                    callback_data=f"cliprun:video:{request_id}:{start}:{end}",
                ),
                InlineKeyboardButton(
                    text="🎧 Только аудио",
                    callback_data=f"cliprun:audio:{request_id}:{start}:{end}",
                ),
            ],
            [InlineKeyboardButton(text="✕ Отмена", callback_data="clipcancel")],
        ]
    )
    await message.answer(
        f"Фрагмент: {_format_time(start)}–{_format_time(end)}\n"
        f"Длительность: {_human_duration(end - start)}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("cliprun:"))
async def run_clip(
    callback: CallbackQuery,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not await _service_available(callback.message, callback.from_user, settings, storage):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5 or parts[1] not in {"video", "audio"}:
        await callback.message.answer("Некорректные параметры фрагмента.")
        return
    try:
        request_id, start, end = map(int, parts[2:])
    except ValueError:
        await callback.message.answer("Некорректные таймкоды.")
        return
    request = storage.media_request(request_id)
    if request is None or request.user_id != callback.from_user.id:
        await callback.message.answer("Исходная ссылка устарела. Пришли её ещё раз.")
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    status = await callback.message.answer("✂️ Подготавливаю фрагмент…")
    media = None
    started_at = perf_counter()
    daily_limit = None
    if callback.from_user.id not in settings.admin_user_ids:
        daily_limit = _user_access(callback.from_user.id, settings, storage).daily_limit
    try:
        event_id = storage.start_download(
            callback.from_user.id,
            callback.from_user.username,
            request.source_id,
            parts[1],
            platform=request.platform,
            daily_limit=daily_limit,
        )
    except LimitReachedError:
        await status.edit_text("Дневной лимит исчерпан. Посмотреть остаток можно командой /quota.")
        return
    try:
        media = await download_media(
            request.source_url,
            kind=parts[1],
            max_bytes=settings.max_upload_bytes,
            timeout_seconds=settings.download_timeout_seconds,
            clip_range=(start, end),
        )
        document = FSInputFile(media.path, filename=media.path.name)
        if parts[1] == "audio":
            await callback.message.answer_audio(document, title=media.title)
        else:
            await callback.message.answer_video(
                document,
                caption=f"{media.title}\n{_format_time(start)}–{_format_time(end)}",
                supports_streaming=True,
            )
        storage.finish_download(
            event_id,
            "success",
            bytes_sent=media.path.stat().st_size,
            duration_ms=_elapsed_ms(started_at),
        )
        await status.delete()
        await callback.message.answer(
            "✅ Фрагмент готов.",
            reply_markup=_post_download_keyboard(request_id),
        )
    except FileTooLargeError:
        storage.finish_download(
            event_id,
            "too_large",
            duration_ms=_elapsed_ms(started_at),
            error_code="too_large",
        )
        await status.edit_text("Фрагмент всё ещё не помещается в лимит Telegram.")
    except DownloadError as exc:
        storage.finish_download(
            event_id,
            "download_error",
            duration_ms=_elapsed_ms(started_at),
            error_code=type(exc).__name__,
        )
        await status.edit_text(_download_error_message(exc, request.platform.title()))
    except Exception as exc:
        storage.finish_download(
            event_id,
            "internal_error",
            duration_ms=_elapsed_ms(started_at),
            error_code=type(exc).__name__,
        )
        logger.exception("Unexpected clip failure for %s:%s", request.platform, request.source_id)
        await status.edit_text("Не удалось подготовить фрагмент. Попробуй ещё раз позже.")
    finally:
        if media is not None:
            media.cleanup()


@router.callback_query(F.data.startswith("posthide:"))
async def hide_post_menu(callback: CallbackQuery, storage: UsageStorage) -> None:
    await callback.answer()
    try:
        request_id = int((callback.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        request_id = 0
    if request_id:
        request = storage.media_request(request_id)
        if request is not None and request.user_id == callback.from_user.id:
            storage.delete_media_request(request_id)
    if callback.message is not None:
        await callback.message.edit_text("✅ Готово")


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

    kind = parts[1]
    try:
        request_id = int(parts[2])
    except ValueError:
        await callback.message.answer("Некорректный запрос загрузки.")
        return
    request = storage.media_request(request_id)
    if request is None or request.user_id != callback.from_user.id:
        await callback.message.answer("Запрос устарел. Пришли ссылку ещё раз.")
        return
    if storage.is_source_blocked(request.platform, request.source_id):
        await callback.message.answer("Этот материал недоступен по результатам жалобы.")
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
            request.source_id,
            kind,
            platform=request.platform,
            daily_limit=daily_limit,
        )
    except LimitReachedError:
        storage.delete_media_request(request_id)
        await status.edit_text("Дневной лимит исчерпан. Посмотреть остаток можно командой /quota.")
        return
    progress_queue: asyncio.Queue[int] = asyncio.Queue()
    event_loop = asyncio.get_running_loop()

    def progress_callback(percent: int) -> None:
        event_loop.call_soon_threadsafe(progress_queue.put_nowait, percent)

    progress_task = asyncio.create_task(_show_progress(status, progress_queue))
    try:
        try:
            media = await download_media(
                request.source_url,
                kind=kind,
                max_bytes=settings.max_upload_bytes,
                timeout_seconds=settings.download_timeout_seconds,
                progress_callback=progress_callback,
            )
        finally:
            progress_task.cancel()
            await asyncio.gather(progress_task, return_exceptions=True)

        document = FSInputFile(media.path, filename=media.path.name)
        report_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data=f"report:{event_id}")]
            ]
        )
        if kind == "audio":
            await callback.message.answer_audio(
                document,
                title=media.title,
                reply_markup=report_keyboard,
            )
        else:
            await callback.message.answer_video(
                document,
                caption=media.title,
                supports_streaming=True,
                reply_markup=report_keyboard,
            )
        storage.finish_download(
            event_id,
            "success",
            bytes_sent=media.path.stat().st_size,
            duration_ms=_elapsed_ms(started_at),
        )
        await status.delete()
        await callback.message.answer(
            "✅ Готово. Что-нибудь ещё?",
            reply_markup=_post_download_keyboard(request_id),
        )
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
        logger.exception(
            "Download failed for %s:%s: %s",
            request.platform,
            request.source_id,
            exc,
        )
        await status.edit_text(_download_error_message(exc, request.platform.title()))
    except Exception as exc:
        storage.finish_download(
            event_id,
            "internal_error",
            duration_ms=_elapsed_ms(started_at),
            error_code=type(exc).__name__,
        )
        logger.exception("Unexpected failure for %s:%s", request.platform, request.source_id)
        await status.edit_text("Произошла внутренняя ошибка. Попробуй немного позже.")
    finally:
        if media is not None:
            media.cleanup()


@router.callback_query(F.data.startswith("report:"))
async def report(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    event_id = (callback.data or "").split(":", 1)[-1]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"reportreason:{event_id}:{code}",
                )
            ]
            for code, label in REPORT_REASONS.items()
        ]
    )
    await callback.message.answer("Выбери причину жалобы:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("reportreason:"))
async def report_reason(
    callback: CallbackQuery,
    settings: Settings,
    storage: UsageStorage,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[2] not in REPORT_REASONS:
        await callback.message.answer("Не удалось зарегистрировать жалобу.")
        return
    try:
        event_id = int(parts[1])
    except ValueError:
        await callback.message.answer("Не удалось зарегистрировать жалобу.")
        return
    complaint = storage.create_complaint(
        event_id,
        callback.from_user.id,
        parts[2],
    )
    if complaint is None:
        await callback.message.answer("Материал для жалобы не найден.")
        return
    await callback.message.answer("Жалоба принята. Спасибо.")
    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать материал",
                    callback_data=f"reportadmin:block:{complaint.id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"reportadmin:dismiss:{complaint.id}",
                ),
            ]
        ]
    )
    for admin_id in settings.admin_user_ids:
        await bot.send_message(
            admin_id,
            f"Новая жалоба #{complaint.id}\n"
            f"Площадка: {complaint.platform}\n"
            f"Материал: {complaint.source_id}\n"
            f"Заявитель: {complaint.reporter_id}\n"
            f"Причина: {REPORT_REASONS[complaint.reason]}",
            reply_markup=admin_keyboard,
        )


@router.callback_query(F.data.startswith("reportadmin:"))
async def report_admin(
    callback: CallbackQuery,
    settings: Settings,
    storage: UsageStorage,
) -> None:
    await callback.answer()
    if callback.message is None or not _is_admin(callback.from_user, settings):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"block", "dismiss"}:
        return
    try:
        complaint_id = int(parts[2])
    except ValueError:
        return
    resolved = storage.resolve_complaint(
        complaint_id,
        block_source=parts[1] == "block",
    )
    if resolved:
        result = "Материал заблокирован." if parts[1] == "block" else "Жалоба отклонена."
        await callback.message.edit_text(f"{callback.message.text}\n\n{result}")


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


async def _show_progress(status: Message, queue: asyncio.Queue[int]) -> None:
    last_bucket = 0
    while True:
        percent = await queue.get()
        bucket = min(percent // 10 * 10, 100)
        if bucket <= last_bucket:
            continue
        last_bucket = bucket
        filled = bucket // 10
        bar = "█" * filled + "░" * (10 - filled)
        try:
            await status.edit_text(f"Загружаю: {bar} {bucket}%")
        except Exception:
            logger.debug("Could not update download progress", exc_info=True)


def _download_error_message(error: DownloadError, platform: str) -> str:
    if isinstance(error, AuthenticationRequiredError):
        return (
            f"{platform} требует авторизацию или публикация закрыта. "
            "Бот работает только с публичными материалами."
        )
    if isinstance(error, RateLimitedError):
        return (
            f"{platform} временно ограничил запросы. "
            "Это не ошибка ссылки — попробуй повторить через несколько минут."
        )
    if isinstance(error, GeoRestrictedError):
        return "Материал недоступен в регионе, где работает бот."
    if isinstance(error, MediaUnavailableError):
        return (
            "Не удалось получить материал: он удалён, закрыт, недоступен "
            "или такой тип публикации пока не поддерживается."
        )
    return (
        "Не удалось загрузить материал из-за ответа площадки. "
        "Попробуй ещё раз позже или пришли другую публичную ссылку."
    )


def _post_download_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✂️ Вырезать фрагмент", callback_data=f"clip:{request_id}")],
            [InlineKeyboardButton(text="✕ Скрыть меню", callback_data=f"posthide:{request_id}")],
        ]
    )


def _parse_clip_range(text: str) -> tuple[int, int] | None:
    parts = re.findall(r"(?<!\d)(\d{1,2}:\d{1,2}(?::\d{1,2})?|\d+)(?!\d)", text)
    if len(parts) != 2:
        return None
    try:
        start, end = (_time_to_seconds(value) for value in parts)
    except ValueError:
        return None
    if start < 0 or end <= start or end - start > 3600:
        return None
    return start, end


def _time_to_seconds(value: str) -> int:
    chunks = [int(chunk) for chunk in value.split(":")]
    if len(chunks) == 1:
        return chunks[0]
    if len(chunks) == 2 and chunks[1] < 60:
        return chunks[0] * 60 + chunks[1]
    if len(chunks) == 3 and chunks[1] < 60 and chunks[2] < 60:
        return chunks[0] * 3600 + chunks[1] * 60 + chunks[2]
    raise ValueError("Invalid timestamp")


def _format_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _human_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    if minutes and secs:
        return f"{minutes} мин {secs} сек"
    if minutes:
        return f"{minutes} мин"
    return f"{secs} сек"


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
