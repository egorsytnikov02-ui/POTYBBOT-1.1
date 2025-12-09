import logging
import os
import re
import datetime
import pytz
import random
import feedparser # 👈 Библиотека для чтения новостей Steam

from threading import Thread
from flask import Flask
from waitress import serve

from upstash_redis import Redis

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode

# --- Фильтр для скрытия токена в логах ---
class TokenFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        token = os.environ.get('TOKEN')
        if token and token in message:
            return False 
        return True

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
for handler in logging.root.handlers:
    handler.addFilter(TokenFilter())
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# ⭐️ Подключение к Redis
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger.info("Успішне підключення до Upstash (Redis)!")
except Exception as e:
    print(f"Критична помилка: Не вдалося підключитися до Upstash (Redis)! {e}")
    exit()

# --- Веб-сервер (Waitress) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот 'ПОТУЖНИЙ' активний!"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    serve(app, host="0.0.0.0", port=port)

# --- КОНСТАНТЫ ---
SCORES_KEY = "potuzhniy_scores"
STEAM_LAST_ID_KEY = "steam_last_news_id" # Ключ для хранения ID последней новости
STEAM_RSS_URL = "https://store.steampowered.com/feeds/news.xml" # Лента новостей

# Ключевые слова для поиска скидок (регистр не важен)
STEAM_KEYWORDS = ['sale', 'fest', 'festival', 'promotion', 'summer', 'winter', 'spring', 'autumn', 'знижки', 'розпродаж']

# --- 🔥 ФРАЗЫ ДЛЯ ОТВЕТА БОТА (REPLY) 🔥 ---
BOT_REPLY_PHRASES = [
    "Іди своєю дорогою, сталкер. Тут немає артефактів для тебе.",
    "Ще одне слово, і я тебе в «Холодець» кину.",
    "Не фони. Мій лічильник Гейгера тріщить від твого крінжу.",
    "Ти шо, безсмертний? Збереження давно робив?",
    "НЕ ТРОГАЙ МЕНЯ, КУСОК МЯСА!",
    "Ти так сміливо пишеш... А дані в «Резерв+» оновив?",
    "Громадянине, пред'явіть військовий квиток або штрих-код!",
    "Я не бачу твоєї електронної декларації. Розмова закінчена.",
    "Запит відхилено. Ти забув вкласти хабар у повідомлення.",
    "Зараз подзвоню в ДТЕК і тебе відключать поза чергою.",
    "У нас дефіцит потужності в енергосистемі, не витрачай мої байти дарма.",
    "МВФ не схвалює твою поведінку. Транш скасовано.",
    "Вийди звідси, розбійник! Ти мене не чуєш?",
    "Я тобі нічого не винен. Я ж не лох якийсь.",
    "Це провокація! Я буду скаржитись в ООН (але їм пофіг)."
]

# --- СПИСКИ ГИФОК ---
POSITIVE_GIF_IDS = [
    'CgACAgIAAyEFAATIovxHAAIDDWkcMy0m8C5AL5UW9vaBZ0JIUHhsAAJkhwACYjrZSAOnzOZuDDU6NgQ',
    'CgACAgQAAyEFAATIovxHAAIDEmkcMy1wQjRBAluj_AXzdQPqkVd0AALZCwACRO1JUBTOazJVNz4lNgQ',
    'CgACAgQAAyEFAATIovxHAAIDE2kcMy3Sq2SRn1idBKYth4GYxSLmAAKBBwAC433cUKZnfhyAKjuVNgQ',
    'CgACAgQAAyEFAATIovxHAAIDFGkcMy2jOW2jpAzJYKvMAcUf820uAAIVBwACME5MUQkcFAABdz9BzjYE',
    'CgACAgQAAyEFAATIovxHAAIDFmkcMy1RSw8Mc2i_WLjrhZY7r62aAAI3BwACKbQMUI-7MMr1sGU5NgQ',
    'CgACAgQAAyEFAATIovxHAAIDFWkcMy3sBmzcsvunOSvq8CqTFeZJAAIoBgACFs_0UWK1EYRe_OceNgQ',
    'CgACAgQAAyEFAATIovxHAAICSmkbZVhc1_Ff9ymU6mj8JzxqmDNXAAIRBwACGVY9Uo0EYWP8LfbBNgQ',
    'CgACAgQAAyEFAATIovxHAAIDGGkcMy1bYuToU-3pbu70GwSg3vFIAAIKBwACGAV1U1fbtsKLFSETNgQ',
    'CgACAgQAAyEFAATIovxHAAIDGWkcMy3E8mqcq9daCAngW1xWAjp7AAL9BgAC0HSMU9zF9CSFB2QjNgQ',
    'CgACAgQAAyEFAATIovxHAAIDGmkcMy3uElNklpmDgBeW35PgFEREAAL0BgACG0V1U0tBqgM4lfk_NgQ',
    'CgACAgQAAyEFAATIovxHAAIDEGkcMy1_JWbQ4AmY0H6iKRGZYOLgAAK5BgACwQ01UG834SxB23AlNgQ'
]

NEGATIVE_GIF_IDS = [
    'CgACAgIAAyEFAATIovxHAAIDDmkcMy2DYcJtlJTkU_ZN02iVPdRSAALIjAACA8jYSHQ4Pa-xroPQNgQ',
    'CgACAgQAAyEFAATIovxHAAIDEWkcMy1XvSbhxGnxdYsLRD6jTHpVAAL6BwACJxdNU_aOqAjhtOajNgQ',
    'CgACAgQAAyEFAATIovxHAAIDG2kcMy2xDXNvCKMmkpjFt9aULAahAAIyCAACixY1U7CC6tw4zC7KNgQ'
]

MORNING_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIDD2kcMy0aLio6iiYYiVEoq0R4xnGnAAJSBwAC9eAsU0GetDmAM6HRNgQ'
]

EVENING_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIDC2kcMDXYBOfejZRHnUImdDOTWgT_AAItBQACasyUUrsEDYn5dujrNgQ'
]

REPLY_TO_BOT_GIF_ID = 'CgACAgIAAyEFAATIovxHAAIBSmkbMaIuOb-D2BxGZdpSf03s1IDcAAJAgwACSL3ZSLtCpogi_5_INgQ'

# --- Вспомогательные функции ---
def load_scores(chat_id):
    try:
        score = redis.hget(SCORES_KEY, chat_id)
        return int(score) if score else 0
    except Exception: return 0

def save_scores(chat_id, new_score):
    try:
        redis.hset(SCORES_KEY, chat_id, str(new_score))
    except Exception: pass

# --- 🎮 STEAM MONITORING ---
async def check_steam_sales(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🎮 Проверка новостей Steam...")
    try:
        feed = feedparser.parse(STEAM_RSS_URL)
        if not feed.entries:
            return

        # Берем самую свежую новость
        latest_entry = feed.entries[0]
        entry_id = latest_entry.id
        title = latest_entry.title
        link = latest_entry.link

        # Проверяем, не отправляли ли мы её уже
        last_sent_id = redis.get(STEAM_LAST_ID_KEY)
        if last_sent_id == entry_id:
            logger.info("Новых событий в Steam нет.")
            return

        # Проверяем ключевые слова
        found_keyword = any(word in title.lower() for word in STEAM_KEYWORDS)
        
        if found_keyword:
            logger.info(f"🔥 Найдено событие Steam: {title}")
            
            # Сохраняем ID, чтобы не спамить
            redis.set(STEAM_LAST_ID_KEY, entry_id)

            # Рассылаем по всем активным чатам
            all_chats = redis.hgetall(SCORES_KEY)
            if not all_chats: return

            text = f"🔥 <b>У Габена нова подія!</b>\n\n🎮 <b>{title}</b>\n\n💸 Готуйте гаманці, сталкери!\n👉 <a href='{link}'>Читати детальніше</a>"

            for chat_id in all_chats.keys():
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Не удалось отправить в чат {chat_id}: {e}")
        else:
            # Если новость не про скидки, просто запоминаем её ID, чтобы не проверять снова
            redis.set(STEAM_LAST_ID_KEY, entry_id)
            logger.info(f"Новость '{title}' пропущена (не про скидки).")

    except Exception as e:
        logger.error(f"Ошибка при проверке Steam: {e}")

# --- Ежедневные сообщения ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    if not EVENING_GIF_IDS: return
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
        text = "Добрий вечір, спільнота! Як у вас з ПОТУЖНІСТЮ?"
        for chat_id in all_chats.keys():
            try:
                await context.bot.send_animation(chat_id=chat_id, animation=random.choice(EVENING_GIF_IDS), caption=text)
            except Exception: pass
    except Exception: pass

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    if not MORNING_GIF_IDS: return
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
        text = "Добрий ранок! Перевірка ПОТУЖНОСТІ."
        for chat_id in all_chats.keys():
            try:
                await context.bot.send_animation(chat_id=chat_id, animation=random.choice(MORNING_GIF_IDS), caption=text)
            except Exception: pass
    except Exception: pass

# --- КОМАНДЫ ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    score = load_scores(chat_id)
    await update.message.reply_text(
        f"📊 <b>Потужність спільноти:</b> <code>{score}</code>",
        parse_mode=ParseMode.HTML
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Тільки адміни!", parse_mode=ParseMode.HTML)
            return
    except Exception: return

    chat_id = str(chat.id)
    save_scores(chat_id, 0)

    await update.message.reply_text(
        "⚠️ <b>ОГОЛОШЕНО ТЕХНІЧНИЙ ДЕФОЛТ!</b>\n\n⚡️ Потужність: <b>0</b>",
        parse_mode=ParseMode.HTML
    )

async def gif_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("🚫 Тільки для адмінів!")
            return
    except Exception: return

    current_status = context.bot_data.get('gif_mode', False)
    new_status = not current_status
    context.bot_data['gif_mode'] = new_status

    status_text = "✅ <b>УВІМКНЕНО</b>" if new_status else "🛑 <b>ВИМКНЕНО</b>"
    await update.message.reply_text(f"🕵️‍♂️ Режим ловлі ID: {status_text}", parse_mode=ParseMode.HTML)

async def get_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('gif_mode', False):
        return
    if not update.message.animation: return
    await update.message.reply_text(
        f"🆔 <b>ID GIF:</b>\n<code>{update.message.animation.file_id}</code>",
        parse_mode=ParseMode.HTML
    )

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat_id = str(update.message.chat_id) 

    # 1. ОТВЕТ НА РЕПЛАЙ
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        try:
            random_phrase = random.choice(BOT_REPLY_PHRASES)
            await update.message.reply_animation(
                animation=REPLY_TO_BOT_GIF_ID,
                caption=random_phrase
            )
        except Exception: pass

    # 2. ИГРА +/-
    if not update.message.text: return
    message_text = update.message.text.strip()

    match = re.search(r'(?:^|\s)([+-])\s*(\d+)', message_text)
    
    if match:
        if not POSITIVE_GIF_IDS or not NEGATIVE_GIF_IDS: return 

        operator = match.group(1)
        try: value = int(match.group(2))
        except ValueError: return

        # 🚜 ПАСХАЛКА 300
        if value == 300:
            await update.message.reply_text(
                "🚜 <b>Я якраз на тракторі, зара приїду до тебе і буде бій.</b>",
                parse_mode=ParseMode.HTML
            )
            return 

        # 🛑 ЛИМИТ > 10
        if value > 10:
            await update.message.reply_text(
                "🛑 <b>А харя не трісне?</b>\nМВФ стільки грошей не виділив. Бюджет урізано, ліміт — 10 очок в одні руки. Май совість!",
                parse_mode=ParseMode.HTML
            )
            return 

        current_score = load_scores(chat_id) 
        new_score = current_score + value if operator == '+' else current_score - value
        
        if operator == '+':
            if value < 0: 
                gif_id = random.choice(NEGATIVE_GIF_IDS)
            else:
                gif_id = random.choice(POSITIVE_GIF_IDS)
        else:
            gif_id = random.choice(NEGATIVE_GIF_IDS)
            
        save_scores(chat_id, new_score) 

        reply_text = f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>"
        try:
            await update.message.reply_animation(animation=gif_id, caption=reply_text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

# --- ЗАПУСК ---
def main_bot():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("gifmode", gif_mode_command))
    
    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
    
    # 🕒 Ежедневные рассылки
    application.job_queue.run_daily(send_evening_message, time=datetime.time(20, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    application.job_queue.run_daily(send_morning_message, time=datetime.time(8, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    
    # 🎮 ПРОВЕРКА STEAM (каждый час = 3600 секунд)
    # Первый запуск через 60 секунд после старта
    application.job_queue.run_repeating(check_steam_sales, interval=3600, first=60)

    print("Бот 'ПОТУЖНИЙ' запущен...")
    application.run_polling()

if __name__ == '__main__':
    if not TOKEN or not UPSTASH_URL:
        print("КРИТИЧЕСКАЯ ОШИБКА: Нет переменных окружения!")
    else:
        server_thread = Thread(target=run_web_server)
        server_thread.daemon = True 
        server_thread.start()
        main_bot()
