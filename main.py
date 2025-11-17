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

# --- Настройки бота ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# --- Подключение к Redis ---
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger = logging.getLogger(__name__)
    logger.info("Успешное подключение к Upstash (Redis)!")
except Exception as e:
    print(f"Критическая ошибка: Не удалось подключиться к Upstash (Redis)! {e}")
    exit()

# --- Веб-сервер ---
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

# 🛡 БЕЗОПАСНОСТЬ: База данных для ТЕСТА
SCORES_KEY = "test_scores"

# ⭐️ ГИФКА ДЛЯ РЕАКЦИИ НА ОТВЕТ ⭐️
REPLY_GIF_ID = 'CgACAgIAAyEFAATIovxHAAIBSmkbMaIuOb-D2BxGZdpSf03s1IDcAAJAgwACSL3ZSLtCpogi_5_INgQ'

# ⭐️ ТЕСТОВЫЕ СПИСКИ (Заглушки, пока ты не добавишь свои)
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
        redis.hset(SCORES_KEY, chat_id, str(new_score))
    except Exception as e:
        logger.error(f"DB Error (Save): {e}")

# --- Помощник для ID ---
async def show_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation:
        file_id = update.message.animation.file_id
        await update.message.reply_text(
            f"<b>ID для коду:</b>\n<code>{file_id}</code>",
            parse_mode=ParseMode.HTML
        )

# --- Рассылки ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
    except: return
    text = "Тест вечір: Як справи?"
    for chat_id in all_chats.keys():
        try:
            gif_id = random.choice(EVENING_GIF_IDS)
            await context.bot.send_animation(chat_id=chat_id, animation=gif_id, caption=text)
        except:
            try: await context.bot.send_message(chat_id=chat_id, text=text)
            except: pass

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
    except: return
    text = "Тест ранок: Прокидаємось!"
    for chat_id in all_chats.keys():
        try:
            gif_id = random.choice(MORNING_GIF_IDS)
            await context.bot.send_animation(chat_id=chat_id, animation=gif_id, caption=text)
        except:
            try: await context.bot.send_message(chat_id=chat_id, text=text)
            except: pass

# --- ⭐️ ОБРАБОТЧИК СООБЩЕНИЙ (С ЛОГИКОЙ ОТВЕТА) ⭐️ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return # Если сообщения нет (редкий случай)
    
    message_text = ""
    if update.message.text:
        message_text = update.message.text.strip()
    
    chat_id = str(update.message.chat_id) 

    # 1. ПРОВЕРКА: Это изменение очков (+/-)?
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
            await update.message.reply_text(f"🧪 Тест: <code>{new_score}</code>", parse_mode=ParseMode.HTML)
        
        return # 👈 Если это были очки, выходим, чтобы не спамить лишний раз

    # 2. ⭐️ ПРОВЕРКА: ЭТО ОТВЕТ (REPLY) НА СООБЩЕНИЕ БОТА? ⭐️
    # Проверяем: есть ли reply, и является ли автор исходного сообщения (from_user.id) самим ботом (context.bot.id)
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        try:
            # Отправляем твою спец-гифку
            await update.message.reply_animation(
                animation=REPLY_GIF_ID,
                caption="👀" # Можно добавить подпись или оставить пустым
            )
        except Exception as e:
            logger.error(f"Не удалось отправить гифку на реплай: {e}")

# --- Запуск ---
def main_bot():
    job_queue = JobQueue()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()
    UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
    
    job_queue.run_daily(send_evening_message, time=datetime.time(hour=20, minute=0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(send_morning_message, time=datetime.time(hour=8, minute=0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))

    # Обработчики (ТЕКСТ + СТИКЕРЫ + ФОТО - чтобы реагировал на любой ответ)
    # filters.ALL ловит всё, но мы фильтруем внутри функции
    application.add_handler(MessageHandler(filters.TEXT | filters.Sticker.ALL | filters.PHOTO, handle_message))
    
    application.add_handler(MessageHandler(filters.ANIMATION, show_gif_id))

    print("TEST BOT (REPLY MODE) запущен...")
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
