from aiogram.filters.state import State, StatesGroup

class MySG(StatesGroup):
    choose_action = State()
    choose_media_type = State()  # Новый стейт для выбора медиа типа
