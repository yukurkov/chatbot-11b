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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветствие и клавиатуру с тремя кнопками."""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📖 Указать прочитанные страницы", callback_data='report_pages')],
        [InlineKeyboardButton("🏋️ Ввести минуты упражнений", callback_data='report_exercise')],
        [InlineKeyboardButton("📊 Мои результаты за неделю", callback_data='show_results')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Выберите действие:",
        reply_markup=reply_markup,
    )
    return REPORT_PAGES

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
        return await show_weekly_results(query)

async def show_weekly_results(query) -> int:
    """Показывает результаты пользователя за текущую неделю."""
    user_id = query.from_user.id
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())  # Понедельник текущей недели
    
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await query.edit_message_text("📊 Данные не найдены. Вы ещё не вводили результаты.")
        return ConversationHandler.END

    user_data = data.get(str(user_id), {})
    pages = user_data.get("pages", [])
    exercise = user_data.get("exercise_minutes", [])

    # Фильтруем записи за текущую неделю
    weekly_pages = [
        entry for entry in pages 
        if datetime.strptime(entry["date"], "%Y-%m-%d %H:%M:%S") >= start_of_week
    ]
    weekly_exercise = [
        entry for entry in exercise 
        if datetime.strptime(entry["date"], "%Y-%m-%d %H:%M:%S") >= start_of_week
    ]

    # Берём последние значения
    last_pages = weekly_pages[-1]["value"] if weekly_pages else 0
    last_exercise = weekly_exercise[-1]["value"] if weekly_exercise else 0

    # Оценка результатов
    if last_pages == 0 and last_exercise == 0:
        message = "📊 Вы ещё не вводили данные за эту неделю."
    else:
        is_good = last_pages >= 200 and last_exercise >= 120
        message = (
            f"📊 Результаты за неделю:\n"
            f"📖 Прочитано страниц: {last_pages}\n"
            f"🏋️ Минут упражнений: {last_exercise}\n\n"
            f"{'✅ Молодчик! Так держать!' if is_good else '➡️ Можно лучше! Ставьте цели и достигайте их!'}"
        )

    await query.edit_message_text(text=message)
    return ConversationHandler.END

async def save_pages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет количество страниц в JSON."""
    return await save_data(update, "pages", "📖 Сохранено: {} страниц.")

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет минуты упражнений в JSON."""
    return await save_data(update, "exercise_minutes", "🏋️ Сохранено: {} минут упражнений.")

async def save_data(update: Update, field: str, success_message: str) -> int:
    """Общая функция для сохранения данных."""
    try:
        value = int(update.message.text)
        if value < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Не кури сюда!**.")
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
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет ввод."""
    await update.message.reply_text("🚫 Действие отменено.")
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
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: None))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
