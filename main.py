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
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters, JobQueue
from telegram.constants import ParseMode

# --- Настройки бота (ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# ⭐️ Подключение к Базе Данных (Redis)
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger = logging.getLogger(__name__)
    logger.info("Успешное подключение к Upstash (Redis)!")
except Exception as e:
    print(f"Критическая ошибка: Не удалось подключиться к Upstash (Redis)! {e}")
    exit()

# --- Веб-сервер (Для UptimeRobot / Cron-job) ---
app = Flask('')
@app.route('/')
def home():
    return "Бот 'ПОТУЖНИЙ' активний!"

def run_web_server():
    # use_reloader=False — обязательно для запуска в потоке!
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False, use_reloader=False)

# --- Логирование ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- КОНСТАНТЫ REDIS ---
SCORES_KEY = "potuzhniy_scores"  # Для игры +/-
XP_KEY_PREFIX = "chat_xp:"       # Для рангов (счетчик сообщений)

# --- ⭐️ НАСТРОЙКИ РАНГОВ ⭐️ ---
RANK_THRESHOLDS = {
    30: {
        "title": "ПОТУЖНІ ГРОМАДЯНИ 💪",
        "msg": "Відчуваєте цей приплив сили? Армія, Мова, Віра і Ваші повідомлення! Вітаємо, тепер Ви — <b>ПОТУЖНІ ГРОМАДЯНИ</b> 💪. Тримайте стрій, спільнота!"
    },
    40: {
        "title": "СХІДНЯКИ 🌅",
        "msg": "Цей чат пройшов горнило і вогонь. Тут більше немає слабких чи випадкових. Тепер Ви — <b>СХІДНЯКИ</b> 🌅. Сонце встає там, де вирішить ваша більшість!"
    },
    50: {
        "title": "ХАРАКТЕРНИКИ ⚔️",
        "msg": "Вашу єдність не беруть ні кулі, ні бани. Ви разом вийшли за межі реальності і бачите майбутнє. Тепер Ви — <b>ХАРАКТЕРНИКИ</b> ⚔️. Цей чат офіційно зачарований!"
    },
    60: {
        "title": "ЗЕЛЕБОБИ 🟢",
        "msg": "Увага! Це кінець епохи бідності (на активність). Ви зробили це разом! Всі на стадіон! Ви — <b>ЗЕЛЕБОБИ</b> 🟢. Ви тут влада, і це ваш чат!"
    }
}

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

# Гифка для реплая боту
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

def get_rank_name(xp):
    if xp < 30: return "ПОРОХОБОТИ 🍫"
    elif 30 <= xp < 40: return "ПОТУЖНІ ГРОМАДЯНИ 💪"
    elif 40 <= xp < 50: return "СХІДНЯКИ 🌅"
    elif 50 <= xp < 60: return "ХАРАКТЕРНИКИ ⚔️"
    else: return "ЗЕЛЕБОБИ 🟢"

# --- Ежедневные задачи ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    if not EVENING_GIF_IDS: return
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
        text = "Добрий вечір ,як у всех з ПОТУЖНІСТЮ ?"
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
        text = "Добрий ранок , як у вас з ПОТУЖНІСТЮ"
        for chat_id in all_chats.keys():
            try:
                await context.bot.send_animation(chat_id=chat_id, animation=random.choice(MORNING_GIF_IDS), caption=text)
            except Exception: pass
    except Exception: pass

# --- КОМАНДЫ ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    try:
        xp_raw = redis.get(f"{XP_KEY_PREFIX}{chat_id}")
        xp = int(xp_raw) if xp_raw else 0
        score = load_scores(chat_id)
    except Exception:
        xp = 0
        score = 0
    rank_name = get_rank_name(xp)
    await update.message.reply_text(
        f"📊 <b>Статистика спільноти</b>\n\n💬 Активність (XP): <b>{xp}</b>\n⚡️ Потужність: <b>{score}</b>\n🏆 Поточний ранг: <b>{rank_name}</b>",
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
    try: redis.set(f"{XP_KEY_PREFIX}{chat_id}", 0)
    except Exception: pass

    await update.message.reply_text(
        "⚠️ <b>ОГОЛОШЕНО ТЕХНІЧНИЙ ДЕФОЛТ!</b>\n\n⚡️ Потужність: <b>0</b>\n🍫 Ранг: <b>ПОРОХОБОТИ</b>",
        parse_mode=ParseMode.HTML
    )

async def gif_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("🚫 Только для админов!")
            return
    except Exception: return

    current_status = context.bot_data.get('gif_mode', False)
    new_status = not current_status
    context.bot_data['gif_mode'] = new_status

    status_text = "✅ <b>ВКЛЮЧЕН</b> (Кидай гифки)" if new_status else "🛑 <b>ВЫКЛЮЧЕН</b>"
    await update.message.reply_text(f"🕵️‍♂️ Режим ловли ID: {status_text}", parse_mode=ParseMode.HTML)

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
    
    # 1. ЛОГИКА РАНГОВ
    try:
        new_xp = redis.incr(f"{XP_KEY_PREFIX}{chat_id}")
        if new_xp in RANK_THRESHOLDS:
            config = RANK_THRESHOLDS[new_xp]
            await context.bot.send_message(chat_id=chat_id, text=config["msg"], parse_mode=ParseMode.HTML)
    except Exception: pass

    # ⭐️ 2. ОТВЕТ НА РЕПЛАЙ БОТУ (С ОСКОРБЛЕНИЕМ)
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        try:
            await update.message.reply_animation(
                animation=REPLY_TO_BOT_GIF_ID,
                caption="НЕ ТРОГАЙ МЕНЯ , КУСОК МЯСА"
            )
        except Exception: pass

    # 3. ЛОГИКА ИГРЫ
    if not update.message.text: return
    message_text = update.message.text.strip()

    # 🔥 ИСПРАВЛЕНИЕ 1: Умная регулярка
    # Ищет совпадение только если это НАЧАЛО строки (^) ИЛИ перед знаком есть ПРОБЕЛ (\s)
    # Это игнорирует минусы внутри ссылок
    match = re.search(r'(?:^|\s)([+-])\s*(\d+)', message_text)
    
    if match:
        if not POSITIVE_GIF_IDS or not NEGATIVE_GIF_IDS: return 

        operator = match.group(1)
        try: value = int(match.group(2))
        except ValueError: return

        # 🔥 ИСПРАВЛЕНИЕ 2: Ограничение макс. 10 очков
        if value > 10:
            value = 10

        bonus_text = ""
        # 🔥 ЛОГИКА ДЛЯ ПЛЮСА
        if operator == '+':
            chance = random.random()
            if 0.60 < chance <= 0.70:
                value = value * 2
                bonus_text = "\n🇺🇸 <b>ПЕРЕМОГА! МВФ дав транш! (x2)</b>"
            elif 0.70 < chance <= 0.80:
                value = value + 20
                bonus_text = "\n🍞 <b>ПЕРЕМОГА! Знайшов заначку Януковича! Але це просто сухарі... (+20)</b>"
            elif 0.80 < chance <= 0.90:
                value = max(1, int(value / 2))
                bonus_text = "\n🤡 <b>ЗРАДА! Половина пішла на відкат... (/2)</b>"
            elif 0.90 < chance <= 0.95:
                value = 0
                bonus_text = "\n👮‍♂️ <b>ЗРАДА! Рахунки заблоковані фінмоніторингом! (0)</b>"
            elif chance > 0.95:
                # ШТРАФ ОТ ГЕТМАНЦЕВА
                value = -50
                bonus_text = "\n📉 <b>ЗРАДА! Гетманцев ввів податок на твої повідомлення! (-50)</b>"

        current_score = load_scores(chat_id) 
        # Если оператор +, прибавляем (но штраф -50 все равно вычтется, так как value отрицательный)
        new_score = current_score + value if operator == '+' else current_score - value
        
        # Выбор гифки
        if operator == '+':
            if value < 0: # Если выпал штраф, шлем негативную гифку
                gif_id = random.choice(NEGATIVE_GIF_IDS)
            else:
                gif_id = random.choice(POSITIVE_GIF_IDS)
        else:
            gif_id = random.choice(NEGATIVE_GIF_IDS)
            
        save_scores(chat_id, new_score) 

        reply_text = f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>{bonus_text}"
        try:
            await update.message.reply_animation(animation=gif_id, caption=reply_text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    
    # 1. ЛОГИКА РАНГОВ
    try:
        new_xp = redis.incr(f"{XP_KEY_PREFIX}{chat_id}")
        if new_xp in RANK_THRESHOLDS:
            config = RANK_THRESHOLDS[new_xp]
            await context.bot.send_message(chat_id=chat_id, text=config["msg"], parse_mode=ParseMode.HTML)
    except Exception: pass

    # ⭐️ 2. ОТВЕТ НА РЕПЛАЙ БОТУ (С ОСКОРБЛЕНИЕМ)
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        try:
            await update.message.reply_animation(
                animation=REPLY_TO_BOT_GIF_ID,
                caption="НЕ ТРОГАЙ МЕНЯ , КУСОК МЯСА"
            )
        except Exception: pass

    # 3. ЛОГИКА ИГРЫ
    if not update.message.text: return
    message_text = update.message.text.strip()

    match = re.search(r'([+-])\s*(\d+)', message_text)
    if match:
        if not POSITIVE_GIF_IDS or not NEGATIVE_GIF_IDS: return 

        operator = match.group(1)
        try: value = int(match.group(2))
        except ValueError: return

        bonus_text = ""
        # 🔥 ЛОГИКА ДЛЯ ПЛЮСА
        if operator == '+':
            chance = random.random()
            if 0.60 < chance <= 0.70:
                value = value * 2
                bonus_text = "\n🇺🇸 <b>ПЕРЕМОГА! МВФ дав транш! (x2)</b>"
            elif 0.70 < chance <= 0.80:
                value = value + 20
                bonus_text = "\n🍞 <b>ПЕРЕМОГА! Знайшов заначку Януковича! Але це просто сухарі... (+20)</b>"
            elif 0.80 < chance <= 0.90:
                value = max(1, int(value / 2))
                bonus_text = "\n🤡 <b>ЗРАДА! Половина пішла на відкат... (/2)</b>"
            elif 0.90 < chance <= 0.95:
                value = 0
                bonus_text = "\n👮‍♂️ <b>ЗРАДА! Рахунки заблоковані фінмоніторингом! (0)</b>"
            elif chance > 0.95:
                # ШТРАФ ОТ ГЕТМАНЦЕВА
                value = -50
                bonus_text = "\n📉 <b>ЗРАДА! Гетманцев ввів податок на твої повідомлення! (-50)</b>"

        current_score = load_scores(chat_id) 
        # Если оператор +, прибавляем (но штраф -50 все равно вычтется)
        new_score = current_score + value if operator == '+' else current_score - value
        
        # Выбор гифки
        if operator == '+':
            if value < 0: # Если выпал штраф, шлем негативную гифку
                gif_id = random.choice(NEGATIVE_GIF_IDS)
            else:
                gif_id = random.choice(POSITIVE_GIF_IDS)
        else:
            gif_id = random.choice(NEGATIVE_GIF_IDS)
            
        save_scores(chat_id, new_score) 

        reply_text = f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>{bonus_text}"
        try:
            await update.message.reply_animation(animation=gif_id, caption=reply_text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

# --- ЗАПУСК ---
def main_bot():
    # Убираем ручное создание JobQueue, библиотека сделает это сама
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("gifmode", gif_mode_command))
    
    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
    # Теперь обращаемся к job_queue через application
    application.job_queue.run_daily(send_evening_message, time=datetime.time(20, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    application.job_queue.run_daily(send_morning_message, time=datetime.time(8, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))

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
