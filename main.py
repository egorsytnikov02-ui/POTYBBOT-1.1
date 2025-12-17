import logging
import os
import re
import datetime
import pytz
import random
import feedparser
import requests

from threading import Thread
from flask import Flask
from waitress import serve

from upstash_redis import Redis

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, MigratedChatError

# --- 1. Настройка логирования ---
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

# --- 2. Переменные окружения ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# --- 3. Подключение к Redis ---
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger.info("✅ Redis підключено!")
except Exception as e:
    logger.error(f"❌ Помилка Redis: {e}")
    exit()

# --- 4. Веб-сервер ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот 'ПОТУЖНИЙ' працює!"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    serve(app, host="0.0.0.0", port=port)

# --- 5. Константы ---
SCORES_KEY = "potuzhniy_scores"

STEAM_LAST_ID_KEY = "steam_last_news_id"
STEAM_RSS_URL = "https://store.steampowered.com/feeds/news.xml"
STEAM_KEYWORDS = [
    'sale', 'fest', 'festival', 'promotion', 'summer', 'winter', 'spring', 'autumn', 
    'знижки', 'розпродаж', 'deal', 'save', 'midweek', 'weekend', 'choice'
]

EPIC_LAST_ID_KEY = "epic_last_giveaway_id"
EPIC_API_URL = "https://www.gamerpower.com/api/giveaways?platform=epic-games-store&type=game&sort-by=date"

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
MORNING_GIF_IDS = ['CgACAgQAAyEFAATIovxHAAIDD2kcMy0aLio6iiYYiVEoq0R4xnGnAAJSBwAC9eAsU0GetDmAM6HRNgQ']
EVENING_GIF_IDS = ['CgACAgQAAyEFAATIovxHAAIDC2kcMDXYBOfejZRHnUImdDOTWgT_AAItBQACasyUUrsEDYn5dujrNgQ']
REPLY_TO_BOT_GIF_ID = 'CgACAgIAAyEFAATIovxHAAIBSmkbMaIuOb-D2BxGZdpSf03s1IDcAAJAgwACSL3ZSLtCpogi_5_INgQ'

# --- 6. Хелперы ---
def load_scores(chat_id):
    try:
        score = redis.hget(SCORES_KEY, chat_id)
        return int(score) if score else 0
    except Exception: return 0

def save_scores(chat_id, new_score):
    try:
        redis.hset(SCORES_KEY, chat_id, str(new_score))
    except Exception: pass

# --- 🤖 Функция "умной" отправки ---
async def safe_send(context, chat_id, text=None, animation=None):
    try:
        if animation:
            await context.bot.send_animation(chat_id=chat_id, animation=animation, caption=text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
    
    except MigratedChatError as e:
        new_id = str(e.new_chat_id)
        logger.info(f"🔄 Миграция чата: {chat_id} -> {new_id}")
        old_score = redis.hget(SCORES_KEY, chat_id)
        if old_score:
            redis.hset(SCORES_KEY, new_id, old_score)
        redis.hdel(SCORES_KEY, chat_id)
        try:
            if animation:
                await context.bot.send_animation(chat_id=new_id, animation=animation, caption=text, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=new_id, text=text, parse_mode=ParseMode.HTML)
        except Exception: pass

    except (BadRequest, Forbidden) as e:
        logger.info(f"🧹 Удаление мертвого чата {chat_id}: {e}")
        redis.hdel(SCORES_KEY, chat_id)
    
    except Exception as e:
        logger.error(f"⚠️ Ошибка отправки в {chat_id}: {e}")

# --- 7. STEAM МОНИТОРИНГ ---
async def check_steam_sales(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🎮 Проверка Steam...")
    try:
        feed = feedparser.parse(STEAM_RSS_URL)
        if not feed.entries: return

        last_sent_id = redis.get(STEAM_LAST_ID_KEY)
        if not last_sent_id:
            try:
                redis.set(STEAM_LAST_ID_KEY, feed.entries[0].id)
            except IndexError: pass
            return

        newest_id = feed.entries[0].id
        found_news = []

        for entry in feed.entries[:10]:
            if entry.id == last_sent_id: break
            if any(word in entry.title.lower() for word in STEAM_KEYWORDS):
                found_news.append((entry.title, entry.link))

        if found_news:
            all_chats = redis.hgetall(SCORES_KEY)
            if all_chats:
                for news_title, news_link in reversed(found_news):
                    text = f"🔥 <b>У Габена нова подія!</b>\n\n🎮 <b>{news_title}</b>\n\n💸 Готуйте гаманці, сталкери!\n👉 <a href='{news_link}'>Читати детальніше</a>"
                    for chat_id in all_chats.keys():
                        await safe_send(context, chat_id, text=text)

        if newest_id != last_sent_id:
            redis.set(STEAM_LAST_ID_KEY, newest_id)

    except Exception as e:
        logger.error(f"Ошибка проверки Steam: {e}")

# --- 8. EPIC GAMES МОНИТОРИНГ ---
async def check_epic_free_games(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🆓 Проверка Epic Games...")
    try:
        response = requests.get(EPIC_API_URL, timeout=10)
        data = response.json()
        if not data: return

        latest_giveaway = data[0]
        giveaway_id = str(latest_giveaway.get('id'))
        
        last_sent_id = redis.get(EPIC_LAST_ID_KEY)
        if last_sent_id == giveaway_id: return

        redis.set(EPIC_LAST_ID_KEY, giveaway_id)

        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return

        text = (
            f"🎁 <b>ХАЛЯВА В EPIC GAMES!</b>\n\n"
            f"🎮 <b>{latest_giveaway.get('title')}</b>\n\n"
            f"⚡️ Забирайте поки дають, сталкери! Це безкоштовно.\n"
            f"👉 <a href='{latest_giveaway.get('open_giveaway_url')}'>ЗАБРАТИ ГРУ</a>"
        )

        for chat_id in all_chats.keys():
            await safe_send(context, chat_id, text=text)

    except Exception as e:
        logger.error(f"Ошибка проверки Epic Games: {e}")

# --- 9. Утро/Вечер ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    if not EVENING_GIF_IDS: return
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
        text = "Добрий вечір, спільнота! Як у вас з ПОТУЖНІСТЮ?"
        for chat_id in all_chats.keys():
            await safe_send(context, chat_id, text=text, animation=random.choice(EVENING_GIF_IDS))
    except Exception: pass

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    if not MORNING_GIF_IDS: return
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
        text = "Добрий ранок! Перевірка ПОТУЖНОСТІ."
        for chat_id in all_chats.keys():
            await safe_send(context, chat_id, text=text, animation=random.choice(MORNING_GIF_IDS))
    except Exception: pass

# --- 10. Команды ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    score = load_scores(chat_id)
    await update.message.reply_text(f"📊 <b>Потужність спільноти:</b> <code>{score}</code>", parse_mode=ParseMode.HTML)

# 🔥 НОВАЯ КОМАНДА ADMIN 🔥
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("🚫 Тільки для адмінів!")
            return
    except Exception: return

    try:
        total_chats = redis.hlen(SCORES_KEY)
        text = f"🤖 <b>СИСТЕМНА ІНФОРМАЦІЯ</b>\n\n📂 <b>Активних чатів:</b> <code>{total_chats}</code>"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Тільки адміни!")
            return
    except Exception: return

    save_scores(str(chat.id), 0)
    await update.message.reply_text("⚠️ <b>ОГОЛОШЕНО ТЕХНІЧНИЙ ДЕФОЛТ!</b>\n\n⚡️ Потужність: <b>0</b>", parse_mode=ParseMode.HTML)

async def gif_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']: return
    except Exception: return
    
    context.bot_data['gif_mode'] = not context.bot_data.get('gif_mode', False)
    text = "✅ <b>УВІМКНЕНО</b>" if context.bot_data['gif_mode'] else "🛑 <b>ВИМКНЕНО</b>"
    await update.message.reply_text(f"🕵️‍♂️ Режим ловлі ID: {text}", parse_mode=ParseMode.HTML)

async def get_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot_data.get('gif_mode', False) and update.message.animation:
        await update.message.reply_text(f"🆔 <b>ID GIF:</b>\n<code>{update.message.animation.file_id}</code>", parse_mode=ParseMode.HTML)

# --- 11. Обработчик ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat_id = str(update.message.chat_id) 

    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        try:
            await update.message.reply_animation(animation=REPLY_TO_BOT_GIF_ID, caption=random.choice(BOT_REPLY_PHRASES))
        except Exception: pass

    if not update.message.text: return
    match = re.search(r'(?:^|\s)([+-])\s*(\d+)', update.message.text.strip())
    
    if match:
        if not POSITIVE_GIF_IDS or not NEGATIVE_GIF_IDS: return 
        operator = match.group(1)
        try: value = int(match.group(2))
        except ValueError: return

        if value == 300:
            await update.message.reply_text("🚜 <b>Я якраз на тракторі, зара приїду до тебе і буде бій.</b>", parse_mode=ParseMode.HTML)
            return 
        
        if value > 10:
            await update.message.reply_text("🛑 <b>А харя не трісне?</b>\nМВФ стільки грошей не виділив. Бюджет урізано, ліміт — 10 очок.", parse_mode=ParseMode.HTML)
            return 

        current_score = load_scores(chat_id) 
        new_score = current_score + value if operator == '+' else current_score - value
        save_scores(chat_id, new_score) 

        gif_id = random.choice(POSITIVE_GIF_IDS if operator == '+' and value >= 0 else NEGATIVE_GIF_IDS)
        try:
            await update.message.reply_animation(animation=gif_id, caption=f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>", parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>", parse_mode=ParseMode.HTML)

# --- 12. ЗАПУСК ---
def main_bot():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("gifmode", gif_mode_command))
    application.add_handler(CommandHandler("admin", admin_command)) # 👈 Зарегистрировали команду
    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    tz = pytz.timezone('Europe/Kyiv')
    
    application.job_queue.run_daily(send_evening_message, time=datetime.time(20, 0, tzinfo=tz), days=(0, 1, 2, 3, 4, 5, 6))
    application.job_queue.run_daily(send_morning_message, time=datetime.time(8, 0, tzinfo=tz), days=(0, 1, 2, 3, 4, 5, 6))
    
    application.job_queue.run_repeating(check_steam_sales, interval=3600, first=60)
    application.job_queue.run_repeating(check_epic_free_games, interval=3600, first=90)

    print("🚀 Бот запущен (с админкой)...")
    application.run_polling()

if __name__ == '__main__':
    if not TOKEN or not UPSTASH_URL:
        print("❌ ОШИБКА: Нет переменных окружения!")
    else:
        server_thread = Thread(target=run_web_server)
        server_thread.daemon = True 
        server_thread.start()
        main_bot()
