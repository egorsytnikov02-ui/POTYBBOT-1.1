import logging
import os
import re
import datetime
import pytz
import random 

from threading import Thread
from flask import Flask

from upstash_redis import Redis

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters, JobQueue
from telegram.constants import ParseMode

# --- Настройки бота (ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# ⭐️ НОВОЕ: Подключение к Базе Данных (Redis)
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger = logging.getLogger(__name__)
    logger.info("Успешное подключение к Upstash (Redis)!")
except Exception as e:
    print(f"Критическая ошибка: Не удалось подключиться к Upstash (Redis)! {e}")
    exit()

# --- Веб-сервер (Для UptimeRobot) ---
app = Flask('')
@app.route('/')
def home():
    return "TEST BOT IS ALIVE"

def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- Логика бота ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 🛡 БЕЗОПАСНОСТЬ: Используем отдельную "папку" для тестов.
# Это гарантирует, что данные основного бота (potuzhniy_scores) НЕ ПОСТРАДАЮТ.
SCORES_KEY = "test_scores"

# ⭐️ ПУСТЫЕ СПИСКИ (С заглушкой, чтобы не было ошибки empty sequence)
# Бот будет слать текст, пока ты не заменишь 'PLACEHOLDER' на реальные ID.
POSITIVE_GIF_IDS = ['PLACEHOLDER']
NEGATIVE_GIF_IDS = ['PLACEHOLDER']
MORNING_GIF_IDS = ['PLACEHOLDER']
EVENING_GIF_IDS = ['PLACEHOLDER']

# --- Работа с БД ---
def load_scores(chat_id):
    try:
        score = redis.hget(SCORES_KEY, chat_id)
        if score is None: return 0
        return int(score)
    except Exception as e:
        logger.error(f"DB Error (Load): {e}")
        return 0

def save_scores(chat_id, new_score):
    try:
        # Только сохранение (hset). Удаления (hdel) здесь нет.
        redis.hset(SCORES_KEY, chat_id, str(new_score))
    except Exception as e:
        logger.error(f"DB Error (Save): {e}")

# --- ⭐️ ПОМОЩНИК: ПОЛУЧЕНИЕ ID ГИФОК ⭐️ ---
async def show_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на ГИФку, показывая ее file_id для ЭТОГО бота."""
    if update.message.animation:
        file_id = update.message.animation.file_id
        await update.message.reply_text(
            f"<b>ID для коду:</b>\n<code>{file_id}</code>",
            parse_mode=ParseMode.HTML
        )

# --- Рассылки ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Test Evening Job...")
    try:
        all_chats = redis.hgetall(SCORES_KEY) # Читаем только тестовые чаты
        if not all_chats: return
    except: return

    text = "Тест вечір: Як справи?"
    for chat_id in all_chats.keys():
        try:
            gif_id = random.choice(EVENING_GIF_IDS)
            await context.bot.send_animation(chat_id=chat_id, animation=gif_id, caption=text)
        except Exception:
            # Если гифка не работает (заглушка), шлем текст
            try: await context.bot.send_message(chat_id=chat_id, text=text)
            except: pass

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Test Morning Job...")
    try:
        all_chats = redis.hgetall(SCORES_KEY) # Читаем только тестовые чаты
        if not all_chats: return
    except: return

    text = "Тест ранок: Прокидаємось!"
    for chat_id in all_chats.keys():
        try:
            gif_id = random.choice(MORNING_GIF_IDS)
            await context.bot.send_animation(chat_id=chat_id, animation=gif_id, caption=text)
        except Exception:
            try: await context.bot.send_message(chat_id=chat_id, text=text)
            except: pass

# --- Обработка сообщений (+/-) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    message_text = update.message.text.strip()
    chat_id = str(update.message.chat_id) 

    match = re.search(r'([+-])\s*(\d+)', message_text)

    if match:
        operator = match.group(1)
        try: value = int(match.group(2))
        except ValueError: return

        current_score = load_scores(chat_id) 

        if operator == '+': 
            new_score = current_score + value
            gif_id = random.choice(POSITIVE_GIF_IDS)
        else: 
            new_score = current_score - value
            gif_id = random.choice(NEGATIVE_GIF_IDS)

        save_scores(chat_id, new_score) 

        try:
            await update.message.reply_animation(
                animation=gif_id,
                caption=f"🧪 Тест: <code>{new_score}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            # Если ID гифки нет или он неправильный, просто шлем текст
            logger.warning(f"Gif error: {e}")
            await update.message.reply_text(
                f"🧪 Тест: <code>{new_score}</code>",
                parse_mode=ParseMode.HTML
            )

# --- Запуск ---
def main_bot():
    job_queue = JobQueue()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()

    UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
    
    # Таймеры
    job_queue.run_daily(send_evening_message, time=datetime.time(hour=20, minute=0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(send_morning_message, time=datetime.time(hour=8, minute=0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))

    # Обработчики
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ⭐️ ВКЛЮЧЕН ПОМОЩНИК ДЛЯ СБОРА ID
    application.add_handler(MessageHandler(filters.ANIMATION, show_gif_id))

    print("TEST BOT (SAFE MODE) запущен...")
    application.run_polling()

if __name__ == '__main__':
    if not TOKEN or not UPSTASH_URL or not UPSTASH_TOKEN:
        print("КРИТИЧЕСКАЯ ОШИБКА: Нет токенов!")
    else:
        print("Запуск веб-сервера...")
        server_thread = Thread(target=run_web_server)
        server_thread.daemon = True 
        server_thread.start()

        main_bot()
