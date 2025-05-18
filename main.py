import logging
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Константы
REPORT_PAGES, REPORT_EXERCISE = range(2)
JSON_DIR = "/mount/dir"
JSON_FILE = Path(JSON_DIR) / "user_data.json"

# Создаём директорию, если её нет
os.makedirs(JSON_DIR, exist_ok=True)

async def show_start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает стартовое меню с тремя кнопками."""
    keyboard = [
        [InlineKeyboardButton("📖 Указать прочитанные страницы", callback_data='report_pages')],
        [InlineKeyboardButton("🏋️ Ввести минуты упражнений", callback_data='report_exercise')],
        [InlineKeyboardButton("📊 Мои результаты за неделю", callback_data='show_results')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(
            text="Выберите действие:",
            reply_markup=reply_markup
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветствие и показывает стартовое меню."""
    user = update.effective_user
    await update.message.reply_html(rf"Привет, {user.mention_html()}!")
    await show_start_menu(update, context)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатие кнопок."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'report_pages':
        await query.edit_message_text(text="📝 Введите количество прочитанных страниц за эту неделю:")
        return REPORT_PAGES
    elif query.data == 'report_exercise':
        await query.edit_message_text(text="⏱ Введите количество минут упражнений за эту неделю:")
        return REPORT_EXERCISE
    elif query.data == 'show_results':
        return await show_weekly_results(query, context)

async def show_weekly_results(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает результаты пользователя за текущую неделю."""
    user_id = query.from_user.id
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await query.edit_message_text("📊 Данные не найдены. Вы ещё не вводили результаты.")
        await show_start_menu(query, context)
        return ConversationHandler.END

    user_data = data.get(str(user_id), {})
    pages = user_data.get("pages", [])
    exercise = user_data.get("exercise_minutes", [])

    weekly_pages = [
        entry for entry in pages 
        if datetime.strptime(entry["date"], "%Y-%m-%d %H:%M:%S") >= start_of_week
    ]
    weekly_exercise = [
        entry for entry in exercise 
        if datetime.strptime(entry["date"], "%Y-%m-%d %H:%M:%S") >= start_of_week
    ]

    total_pages = sum(entry["value"] for entry in weekly_pages)
    total_exercise = sum(entry["value"] for entry in weekly_exercise)

    if total_pages == 0 and total_exercise == 0:
        message = "📊 Вы ещё не вводили данные за эту неделю."
    else:
        is_good = total_pages >= 200 and total_exercise >= 120
        message = (
            f"📊 Ваши результаты за неделю:\n"
            f"📖 Всего прочитано страниц: {total_pages}\n"
            f"🏋️ Всего минут упражнений: {total_exercise}\n\n"
            f"{'✅ Молодец! Так держать!' if is_good else '➡️ Можно лучше! Ставьте цели и достигайте их!'}"
        )

    await query.edit_message_text(text=message)
    await show_start_menu(query, context)
    return ConversationHandler.END

async def save_pages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет количество страниц в JSON."""
    return await save_data(update, context, "pages", "📖 Сохранено: {} страниц.")

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет минуты упражнений в JSON."""
    return await save_data(update, context, "exercise_minutes", "🏋️ Сохранено: {} минут упражнений.")

async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, success_message: str) -> int:
    """Общая функция для сохранения данных."""
    try:
        value = int(update.message.text)
        if value < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите положительное число.")
        return REPORT_PAGES if field == "pages" else REPORT_EXERCISE

    user_id = update.effective_user.id
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if str(user_id) not in data:
        data[str(user_id)] = {"pages": [], "exercise_minutes": []}
    
    data[str(user_id)][field].append({
        "date": current_date,
        "value": value,
    })

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    await update.message.reply_text(success_message.format(value))
    await show_start_menu(update, context)
    return ConversationHandler.END

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает произвольные сообщения пользователя."""
    await update.message.reply_text("🤖 Я пока не умею поддерживать диалоги.")
    await show_start_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет ввод."""
    await update.message.reply_text("🚫 Действие отменено.")
    await show_start_menu(update, context)
    return ConversationHandler.END

def main() -> None:
    """Запуск бота."""
    application = Application.builder().token(os.environ.get("TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REPORT_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_pages)],
            REPORT_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_exercise)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик для произвольных сообщений
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message), group=1)
    
    # Обработчики команд и callback-ов (идут с более высоким приоритетом)
    application.add_handler(conv_handler, group=2)
    application.add_handler(CallbackQueryHandler(button_callback), group=2)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
