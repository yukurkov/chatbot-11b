import logging
import os
from datetime import time, datetime
from typing import Dict

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackContext,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global storage for chat reminders settings
chat_settings: Dict[int, Dict[str, str]] = {}

DEFAULT_DAY = "Sunday"
DEFAULT_TIME = time(hour=17, minute=0)  # 17:00 Moscow time

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    if update.effective_chat.type == "private":
        await update.message.reply_text("Добавь меня в группу, и я буду напоминать о важных вещах!")
    else:
        user = update.effective_user
        await update.message.reply_text(
            f"Привет {user.mention_html()}! Я бот-напоминатель. "
            f"Я буду напоминать о челлендже каждое {DEFAULT_DAY} в {DEFAULT_TIME.strftime('%H:%M')} (МСК). "
            "Используй /setreminder чтобы изменить время напоминаний.",
            parse_mode="HTML"
        )
        # Initialize default settings for the chat
        chat_id = update.effective_chat.id
        chat_settings[chat_id] = {
            "day": DEFAULT_DAY,
            "time": DEFAULT_TIME.strftime("%H:%M")
        }
        # Schedule the job
        schedule_weekly_reminder(context.application, chat_id)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start - начать работу с ботом\n"
        "/setreminder - установить день и время напоминания\n"
        "/help - показать это сообщение"
    )

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the reminder day and time."""
    if update.effective_chat.type == "private":
        await update.message.reply_text("Эта команда работает только в группах!")
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /setreminder <день недели> <часы:минуты>\n"
            "Пример: /setreminder Sunday 17:00"
        )
        return

    try:
        day = context.args[0].capitalize()
        time_str = context.args[1]
        
        # Validate day
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if day not in days:
            raise ValueError("Неверный день недели")
        
        # Validate time
        hours, minutes = map(int, time_str.split(':'))
        if not (0 <= hours < 24 and 0 <= minutes < 60):
            raise ValueError("Неверное время")
        
        # Save settings
        chat_id = update.effective_chat.id
        chat_settings[chat_id] = {
            "day": day,
            "time": time_str
        }
        
        # Reschedule the job
        schedule_weekly_reminder(context.application, chat_id)
        
        await update.message.reply_text(
            f"Напоминание установлено на каждый {day} в {time_str} (МСК)"
        )
    except (IndexError, ValueError) as e:
        await update.message.reply_text(f"Ошибка: {str(e)}\nПопробуйте снова.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all messages."""
    if update.effective_chat.type == "private":
        await update.message.reply_text("Добавь меня в группу, и я буду напоминать о важных вещах!")
    elif (
        update.message and 
        update.message.text and 
        "@" + context.bot.username.lower() in update.message.text.lower()
    ):
        chat_id = update.effective_chat.id
        settings = chat_settings.get(chat_id, {
            "day": DEFAULT_DAY,
            "time": DEFAULT_TIME.strftime("%H:%M")
        })
        await update.message.reply_text(
            f"Я тут, чтобы напомнить вам о челлендже. "
            f"Напоминаю каждую {settings['day']} в {settings['time']} (МСК)."
        )

async def send_weekly_reminder(context: CallbackContext) -> None:
    """Send the weekly reminder to the chat."""
    job = context.job
    chat_id = job.chat_id
    
    try:
        # Get all chat members except bots
        members = await context.bot.get_chat_administrators(chat_id)
        mentions = []
        for member in members:
            if not member.user.is_bot:
                mentions.append(member.user.mention_html())
        
        if mentions:
            message = "Всем привет! " + ", ".join(mentions) + "\n"
            message += "Напишите, сколько вы прочитали за эту неделю и сколько минут упражнений выполнили."
            await context.bot.send_message(chat_id, message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending reminder to chat {chat_id}: {e}")

def schedule_weekly_reminder(application: Application, chat_id: int) -> None:
    """Schedule or reschedule the weekly reminder for a chat."""
    # Remove existing job if any
    current_jobs = application.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()
    
    # Get settings for this chat or use defaults
    settings = chat_settings.get(chat_id, {
        "day": DEFAULT_DAY,
        "time": DEFAULT_TIME.strftime("%H:%M")
    })
    
    # Parse time
    hours, minutes = map(int, settings["time"].split(':'))
    reminder_time = time(hour=hours, minute=minutes, tzinfo=datetime.now().astimezone().tzinfo)
    
    # Schedule new job
    application.job_queue.run_repeating(
        send_weekly_reminder,
        interval=604800,  # 1 week in seconds
        first_time=reminder_time,
        chat_id=chat_id,
        name=str(chat_id),
        data={"day": settings["day"]}
    )

def main() -> None:
    """Start the bot."""
    token = os.environ.get("TOKEN")
    if not token:
        raise ValueError("Необходимо установить переменную окружения TOKEN")
    
    application = Application.builder().token(token).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setreminder", set_reminder))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
