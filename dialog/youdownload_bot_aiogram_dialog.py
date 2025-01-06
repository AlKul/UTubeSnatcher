import logging
import os

import asyncio 
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from states.states import *


from aiogram_dialog import Dialog

from aiogram.filters import Command
from aiogram.types import Message

from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog import setup_dialogs
from aiogram import Bot, Dispatcher, types, Router, F

from logger.logger import logger  


from handlers.handlers import start_router  # Импортируем функцию регистрации
# from handlers.download_handler_dialog import download_router, MySG
from handlers.download_handler_dialog import download_router#, DialogSG
# from handlers.download_handler import download_router, MySG

from aiogram import Router


# # Настраиваем логирование
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

storage = MemoryStorage()
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)

def register_routers(dp: Dispatcher) -> None:
    """Registers routers"""

    dp.include_router(start_router)    
    dp.include_router(download_router)
    setup_dialogs(dp)
    


async def main() -> None:
    """The main function which will execute our event loop and start polling."""
    
    dp = Dispatcher(storage=storage)
    register_routers(dp)
    await dp.start_polling(bot)
    

if __name__ == "__main__":
    asyncio.run(main())