import logging
import os

from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery
from aiogram import Bot, Dispatcher, types, Router, F

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Start
from aiogram_dialog.widgets.text import Const
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from aiogram_dialog import (
    Dialog, DialogManager, setup_dialogs, StartMode, Window,
)
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const


from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.text import Const

from aiogram.filters.state import StatesGroup, State

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Back, Next, Row, SwitchTo
from aiogram_dialog.widgets.text import Const

from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Start
from aiogram_dialog.widgets.text import Const


# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



class DialogSG(StatesGroup):
    first = State()


download_router = Router()
# setup_dialogs(download_router)

# Хэндлер для обработки текстового сообщения с ссылкой на видео
@download_router.message()
async def test_handler(message: types.Message, dialog_manager: DialogManager):
    await message.reply(f"Произошла ошибка: {str(message.text)}")

dialog = Dialog(
    Window(
        Const("Что вы хотите скачать?"),
        Row(
            Button(Const("Видео"), id="video"),
            Button(Const("Аудио"), id="audio"),
        ),
        state=DialogSG.first,
    )
)

setup_dialogs(download_router)