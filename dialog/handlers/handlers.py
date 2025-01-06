import re 

from aiogram.filters import Command
from aiogram.types import Message

from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog import setup_dialogs
from aiogram import Bot, Dispatcher, types, Router, F

from logger.logger import logger

# from youdownload_bot_aiogram_dialog import dp

start_router = Router()

@start_router.message(Command('start'))
async def cmd_start(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    await message.answer("Привет! Отправь мне ссылку на YouTube-видео, и я помогу тебе его скачать.\nВ ближайших планах расширение функционала на Tik-tok и Instagram, а также увеличение стабильности.")


@start_router.message(Command('start2'))
async def cmd_start(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    await message.answer(f"Привет, {message.from_user.first_name}! Отправь мне ссылку на YouTube-видео, и я помогу тебе его скачать.\nВ ближайших планах расширение функционала на Tik-tok и Instagram, а также увеличение стабильности.")


# download_router = Router()

# # Регулярка для проверки ссылок
# url_pattern = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be|tiktok\.com|instagram\.com)/[\w\-\.]+")

# @download_router.message(lambda message: url_pattern.match(message.text))
# async def cmd_download(message: types.Message):
#     logger.info(f"User {message.from_user.id} sent a link: {message.text}")
#     await message.answer(f"Your link: {message.text}")
