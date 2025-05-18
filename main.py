import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext,
    MessageHandler, Filters
)
from datetime import datetime, time
import pytz
import json
import os
from collections import defaultdict

# Конфигурация бота
TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
CHAT_ID = 'YOUR_GROUP_CHAT_ID'  # ID общего чата
ADMIN_ID = 'YOUR_ADMIN_ID'  # ID администратора для отладки

# Жестко зафиксированные участники
PARTICIPANTS = {
    'user1_id': {'name': 'Участник 1', 'pages_goal': 50, 'workout_goal': 5},
    'user2_id': {'name': 'Участник 2', 'pages_goal': 50, 'workout_goal': 5},
    'user3_id': {'name': 'Участник 3', 'pages_goal': 50, 'workout_goal': 5},
    'user4_id': {'name': 'Участник 4', 'pages_goal': 50, 'workout_goal': 5},
    'user5_id': {'name': 'Участник 5', 'pages_goal': 50, 'workout_goal': 5},
}

# Файл для хранения данных
DATA_FILE = 'weekly_data.json'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка данных из файла
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'weekly_results': []}

# Сохранение данных в файл
def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Отправка вопросов участникам
def ask_participants(context: CallbackContext):
    data = load_data()
    current_week = datetime.now().strftime("%Y-%U")
    
    # Проверяем, не отправляли ли уже вопросы на этой неделе
    if data.get('weekly_results') and data['weekly_results'][-1].get('week') == current_week:
        return
    
    # Создаем запись для текущей недели
    if not data.get('weekly_results') or data['weekly_results'][-1].get('week') != current_week:
        data['weekly_results'].append({
            'week': current_week,
            'participants': {}
        })
        save_data(data)
    
    for user_id in PARTICIPANTS:
        try:
            keyboard = [
                [InlineKeyboardButton("Ввести данные", callback_data=f"input_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.bot.send_message(
                chat_id=user_id,
                text=f"Привет, {PARTICIPANTS[user_id]['name']}! Пожалуйста, отправь свои результаты за неделю:\n"
                     f"1. Количество прочитанных страниц\n"
                     f"2. Количество часов тренировок\n"
                     f"Цели на неделю: {PARTICIPANTS[user_id]['pages_goal']} страниц, {PARTICIPANTS[user_id]['workout_goal']} часов тренировок.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
            context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Ошибка при отправке сообщения пользователю {PARTICIPANTS[user_id]['name']}: {e}"
            )

# Напоминание тем, кто не ответил
def send_reminders(context: CallbackContext):
    data = load_data()
    current_week = datetime.now().strftime("%Y-%U")
    
    if not data.get('weekly_results') or data['weekly_results'][-1].get('week') != current_week:
        return
    
    current_week_data = data['weekly_results'][-1]
    
    for user_id in PARTICIPANTS:
        if str(user_id) not in current_week_data['participants']:
            try:
                context.bot.send_message(
                    chat_id=user_id,
                    text="Напоминание: пожалуйста, отправь свои результаты за неделю!"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")

# Публикация результатов в общий чат
def publish_results(context: CallbackContext):
    data = load_data()
    current_week = datetime.now().strftime("%Y-%U")
    
    if not data.get('weekly_results') or data['weekly_results'][-1].get('week') != current_week:
        return
    
    current_week_data = data['weekly_results'][-1]
    results = []
    
    for user_id, user_data in PARTICIPANTS.items():
        user_results = current_week_data['participants'].get(str(user_id), {})
        pages = user_results.get('pages', 0)
        workout = user_results.get('workout', 0)
        
        # Определяем медаль
        pages_goal = user_data['pages_goal']
        workout_goal = user_data['workout_goal']
        
        pages_percent = pages / pages_goal
        workout_percent = workout / workout_goal
        
        if pages_percent >= 1 and workout_percent >= 1:
            medal = "🥇"
        elif pages_percent >= 0.5 and workout_percent >= 0.5:
            medal = "🥈"
        elif pages_percent >= 0.5 or workout_percent >= 0.5:
            medal = "🥉"
        else:
            medal = ""
        
        results.append(
            f"{user_data['name']}: {pages} стр. ({pages_percent:.0%}), "
            f"{workout} ч. ({workout_percent:.0%}) {medal}"
        )
    
    # Добавляем статистику за последние 5 недель
    stats_message = "\n\nСтатистика за последние 5 недель:\n"
    weeks_to_show = data['weekly_results'][-5:]
    
    for week_data in weeks_to_show:
        week_name = week_data['week']
        week_participants = week_data.get('participants', {})
        total_pages = sum(p.get('pages', 0) for p in week_participants.values())
        total_workout = sum(p.get('workout', 0) for p in week_participants.values())
        
        stats_message += (
            f"Неделя {week_name}: "
            f"Всего {total_pages} стр., {total_workout} ч. тренировок\n"
        )
    
    # Сравнение с предыдущей неделей
    if len(data['weekly_results']) >= 2:
        prev_week = data['weekly_results'][-2]
        prev_pages = sum(p.get('pages', 0) for p in prev_week.get('participants', {}).values())
        prev_workout = sum(p.get('workout', 0) for p in prev_week.get('participants', {}).values())
        
        current_pages = sum(p.get('pages', 0) for p in current_week_data.get('participants', {}).values())
        current_workout = sum(p.get('workout', 0) for p in current_week_data.get('participants', {}).values())
        
        pages_diff = current_pages - prev_pages
        workout_diff = current_workout - prev_workout
        
        trend = "📈 Улучшение" if (pages_diff >= 0 and workout_diff >= 0) else "📉 Ухудшение"
        
        stats_message += (
            f"\nТренд по сравнению с предыдущей неделей: {trend}\n"
            f"Страницы: {'+' if pages_diff >=0 else ''}{pages_diff}\n"
            f"Тренировки: {'+' if workout_diff >=0 else ''}{workout_diff}"
        )
    
    # Отправляем сообщение в общий чат
    try:
        context.bot.send_message(
            chat_id=CHAT_ID,
            text="📊 Результаты за неделю:\n\n" + "\n".join(results) + stats_message
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов в чат: {e}")
        context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Ошибка при отправке результатов в чат: {e}"
        )

# Обработчик кнопки "Ввести данные"
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.data.split('_')[1]
    if str(update.effective_user.id) != user_id:
        query.edit_message_text(text="Это сообщение не для вас!")
        return
    
    query.edit_message_text(text="Пожалуйста, отправьте свои результаты в формате: страницы часы\nНапример: 45 3.5")

# Обработчик текстовых сообщений с результатами
def handle_results(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    
    if user_id not in PARTICIPANTS:
        update.message.reply_text("Вы не являетесь участником этого отслеживания.")
        return
    
    try:
        pages, workout = map(float, update.message.text.split())
    except:
        update.message.reply_text("Пожалуйста, отправьте данные в формате: страницы часы\nНапример: 45 3.5")
        return
    
    data = load_data()
    current_week = datetime.now().strftime("%Y-%U")
    
    if not data.get('weekly_results') or data['weekly_results'][-1].get('week') != current_week:
        update.message.reply_text("Сейчас не время для отправки результатов. Ждите воскресенья!")
        return
    
    # Сохраняем результаты
    data['weekly_results'][-1]['participants'][user_id] = {
        'pages': pages,
        'workout': workout,
        'timestamp': datetime.now().isoformat()
    }
    save_data(data)
    
    update.message.reply_text("Спасибо! Ваши результаты сохранены.")

# Команда для администратора для принудительной публикации результатов
def force_publish(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != ADMIN_ID:
        update.message.reply_text("У вас нет прав для этой команды.")
        return
    
    publish_results(context)
    update.message.reply_text("Результаты опубликованы.")

def main():
    # Создаем Updater и передаем ему токен бота
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Регистрируем обработчики
    dp.add_handler(CommandHandler("publish", force_publish))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_results))

    # Настраиваем расписание
    tz = pytz.timezone('Europe/Moscow')
    
    # Воскресенье утром - запрос результатов
    updater.job_queue.run_daily(
        ask_participants,
        time=time(hour=10, minute=0, tzinfo=tz),
        days=(6,)  # 6 - воскресенье (0 - понедельник)
    )
    
    # Воскресенье 17:00 - напоминание
    updater.job_queue.run_daily(
        send_reminders,
        time=time(hour=17, minute=0, tzinfo=tz),
        days=(6,)
    )
    
    # Воскресенье 20:00 - публикация результатов
    updater.job_queue.run_daily(
        publish_results,
        time=time(hour=20, minute=0, tzinfo=tz),
        days=(6,)
    )

    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
