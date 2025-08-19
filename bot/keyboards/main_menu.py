from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def kb_main_menu_admin() -> InlineKeyboardMarkup:

	kb = InlineKeyboardMarkup(row_width=1)
	kb.add(InlineKeyboardButton("📁Главное Меню", callback_data="mm:start"))
	kb.add(InlineKeyboardButton("🔎Справка о боте", callback_data="mm:about"))
	kb.add(InlineKeyboardButton("🎓Табель успеваемости", callback_data="mm:progress"))
	kb.add(InlineKeyboardButton("🔄 Синхронизация БД", callback_data="mm:sync"))
	kb.add(InlineKeyboardButton("🚨 Алерты", callback_data="mm:alerts"))
	return kb


def kb_main_menu_mentor() -> InlineKeyboardMarkup:

	kb = InlineKeyboardMarkup(row_width=1)
	kb.add(InlineKeyboardButton("📁Главное Меню", callback_data="mm:start"))
	kb.add(InlineKeyboardButton("🔎Справка о боте", callback_data="mm:about"))
	kb.add(InlineKeyboardButton("🎓Табель успеваемости", callback_data="mm:progress"))
	return kb


def kb_back_to_main() -> InlineKeyboardMarkup:

	kb = InlineKeyboardMarkup(row_width=1)
	kb.add(InlineKeyboardButton("📁Главное Меню", callback_data="mm:start"))
	return kb
