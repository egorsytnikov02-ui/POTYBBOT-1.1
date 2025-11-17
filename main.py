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
from telegram.error import BadRequest, Forbidden

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

# --- Веб-сервер (Для UptimeRobot) ---
app = Flask('')
@app.route('/')
def home():
    return "Бот 'ПОТУЖНИЙ' активний!"

def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
# ------------------------------------

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
    40: {
        "title": "ПОТУЖНІ ГРОМАДЯНИ 💪",
        "msg": "Відчуваєте цей приплив сили? Армія, Мова, Віра і Ваші повідомлення! Вітаємо, тепер Ви — <b>ПОТУЖНІ ГРОМАДЯНИ</b> 💪. Тримайте стрій, спільнота!"
    },
    80: {
        "title": "СХІДНЯКИ 🌅",
        "msg": "Цей чат пройшов горнило і вогонь. Тут більше немає слабких чи випадкових. Тепер Ви — <b>СХІДНЯКИ</b> 🌅. Сонце встає там, де вирішить ваша більшість!"
    },
    120: {
        "title": "ХАРАКТЕРНИКИ ⚔️",
        "msg": "Вашу єдність не беруть ні кулі, ні бани. Ви разом вийшли за межі реальності і бачите майбутнє. Тепер Ви — <b>ХАРАКТЕРНИКИ</b> ⚔️. Цей чат офіційно зачарований!"
    },
    200: {
        "title": "ЗЕЛЕБОБИ 🟢",
        "msg": "Увага! Це кінець епохи бідності (на активність). Ви зробили це разом! Всі на стадіон! Ви — <b>ЗЕЛЕБОБИ</b> 🟢. Ви тут влада, і це ваш чат!"
    }
}

# --- СПИСКИ ГИФОК (Сюда вставлять новые ID) ---
POSITIVE_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIBMmkbIzBGgizItYUn6o8fZlpqGjtqAAJiAwACTvSFUqxjPD48K-gAATYE',
    'CgACAgQAAyEFAATIovxHAAIBHmkbIaZFLIP_S4833aCn_s-D4BDEAALZCwACRO1JUBpaBRGAwhBvNgQ',
    'CgACAgQAAyEFAATIovxHAAIBIGkbIc3XIkwnqYFgwet3OxYCtTZwAAKBBwAC433cUFBsoYS9IXMkNgQ',
    'CgACAgQAAyEFAATIovxHAAIBImkbIfDxrBTOiprkdrjUjh-UobQiAAIVBwACME5MUZm93-5h-vI6NgQ',
    'CgACAgQAAyEFAATIovxHAAIBJGkbIiIp7dZsQdMlhbrVlXwZY3Y_AAIoBgACFs_0USgd43y068CINgQ',
    'CgACAgQAAyEFAATIovxHAAIBJmkbIkAzqeJQLkUqWugqExioLPycAAI3BwACKbQMULIAAd4-8dO41DYE',
    'CgACAgQAAyEFAATIovxHAAIBKGkbImRTZRMmpgxVOvYu5P5pN1MqAAIRBwACGVY9UqIyuKjywgTFNgQ',
    'CgACAgQAAyEFAATIovxHAAIBKmkbIobxmBVu7jO8b9jB6RHmW73TAAIKBwACGAV1U9NNZdDU0v5yNgQ',
    'CgACAgQAAyEFAATIovxHAAIBLGkbIrJqa2reCTDflu2Ewtx7JkCLAAL9BgAC0HSMU-Tr7ZY7KzoNNgQ',
    'CgACAgQAAyEFAATIovxHAAIBLmkbIuB-FVENCjsqaFIkekzSInH9AAL0BgACG0V1U0ReVATVWXzmNgQ',
    'CgACAgQAAyEFAATIovxHAAIBHGkbIYJHnkyR8eg3wjEVMWLLG1CHAAL6BwACJxdNU6LCCnXidiruNgQ',
    'CgACAgQAAyEFAATIovxHAAIBGmkbIVl25ZMb_AfU7dwGPfOORcfrAAK5BgACwQ01UALpKP9zFPjXNgQ',
    'CgACAgIAAyEFAATIovxHAAIBFGkbIDKVBz0AAcCHPWPiouFBQ-8QUwACZIcAAmI62UjvjUf8zjY5HzYE',
    'CgACAgIAAyEFAATIovxHAAPdaRkVYfGLS8oPv9bQCqI01djvty4AApeHAALH_MhIcSfwdw2VoS82BA',
    'CgACAgIAAyEFAATIovxHAAPbaRkVVbPf905738M4G3LMF2eG5QIAAtWHAALH_MhIO-EsNlzAWLg2BA',
    'CgACAgIAAyEFAATIovxHAAPZaRkVQ0SQ5HVf5JX3ojNQskYlamsAAuGHAALH_MhIYotTm8JAOi02BA',
    'CgACAgIAAyEFAATIovxHAAPXaRkVOZUJovZg4qZMAYtUBDRBDI8AAuWHAALH_MhIZsFR9x5rJqs2BA',
    'CgACAgIAAyEFAATIovxHAAPVaRkVKPCPl8nHUFRqZb4TAaPMDegAAg2IAALH_MhINH831_iMvDw2BA',
    'CgACAgIAAyEFAATIovxHAAPTaRkVIFYwvRjSdtR-xERpuocploYAAhSIAALH_MhId3xCMjhA4Hc2BA',
    'CgACAgIAAyEFAATIovxHAAPRaRkVBwGS3n68R0PKj3nPCf5ST8gAAhWIAALH_MhI-QJJLtNtHIo2BA',
    'CgACAgIAAyEFAATIovxHAAPlaRkXI45rEILHUdlJ_BX0clqDAAF2AAL1iwACdw_ISGFKTQirLN6zNgQ'
]

NEGATIVE_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIBMGkbIwse95wPdE8XZrduCgeAYuN7AAIyCAACixY1U0zP41C7kaTqNgQ',
    'CgACAgIAAyEFAATIovxHAAIBFmkbIQRUp9M5hNU1aOKBZVDO_dCrAALIjAACA8jYSB_SEuxq5JebNgQ',
    'CgACAgIAAyEFAATIovxHAAPnaRkXR25oJvr4YOYNMWVgmtnxHFAAAvaLAAJ3D8hIlSRJkeoXjIU2BA'
]

MORNING_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIBGGkbITuIn7xBN5LjD9yi03KJ1IAGAAJSBwAC9eAsUxHtO0PMUFZ_NgQ',
    'CgACAgIAAyEFAATIovxHAAPfaRkVy_pDWhYQ_ZyHn-zwBE-kmQ8AAhaIAALH_MhIpn-CVf-kYuw2BA',
    'CgACAgIAAyEFAATIovxHAAPhaRkV1tVdDZYUA7UZBCIpRoKHfBgAAumHAALH_MhILWSt8-lICiI2BA'
]

EVENING_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIBNGkbI2amm37CYPfedWFGbP1D3uFyAAItBQACasyUUgXuyrbIgvhkNgQ',
    'CgACAgIAAyEFAATIovxHAAPjaRkWFCSv_DnOVDzksPaHO2czgXsAAt-HAALH_MhIKbxpNmaiw2g2BA'
]

# --- Вспомогательные функции ---
def load_scores(chat_id):
    try:
        score = redis.hget(SCORES_KEY, chat_id)
        return int(score) if score else 0
    except Exception as e:
        logger.error(f"Ошибка чтения очков {chat_id}: {e}")
        return 0

def save_scores(chat_id, new_score):
    try:
        redis.hset(SCORES_KEY, chat_id, str(new_score))
    except Exception as e:
        logger.error(f"Ошибка записи очков {chat_id}: {e}")

def get_rank_name(xp):
    if xp < 40:
        return "ПОРОХОБОТИ 🍫"
    elif 40 <= xp < 80:
        return "ПОТУЖНІ ГРОМАДЯНИ 💪"
    elif 80 <= xp < 120:
        return "СХІДНЯКИ 🌅"
    elif 120 <= xp < 200:
        return "ХАРАКТЕРНИКИ ⚔️"
    else:
        return "ЗЕЛЕБОБИ 🟢"

# --- Ежедневные задачи ---
async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запуск вечірнього повідомлення...")
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
    except Exception: return

    text = "Добрий вечір ,як у всех з ПОТУЖНІСТЮ ?"
    for chat_id in all_chats.keys():
        try:
            await context.bot.send_animation(chat_id=chat_id, animation=random.choice(EVENING_GIF_IDS), caption=text)
        except Exception: pass

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запуск ранкового повідомлення...")
    try:
        all_chats = redis.hgetall(SCORES_KEY)
        if not all_chats: return
    except Exception: return

    text = "Добрий ранок , як у вас з ПОТУЖНІСТЮ"
    for chat_id in all_chats.keys():
        try:
            await context.bot.send_animation(chat_id=chat_id, animation=random.choice(MORNING_GIF_IDS), caption=text)
        except Exception: pass

# --- КОМАНДЫ ---

# 1. Команда /status
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
        f"📊 <b>Статистика спільноти</b>\n\n"
        f"💬 Активність (XP): <b>{xp}</b>\n"
        f"⚡️ Потужність: <b>{score}</b>\n"
        f"🏆 Поточний ранг: <b>{rank_name}</b>",
        parse_mode=ParseMode.HTML
    )

# 2. Команда /reset (ПОЛНЫЙ СБРОС)
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    # Проверка прав
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ <b>Тільки адміністратори можуть оголосити дефолт!</b>", parse_mode=ParseMode.HTML)
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return

    chat_id = str(chat.id)
    
    # Сбрасываем "Потужність" и XP
    save_scores(chat_id, 0)
    try:
        redis.set(f"{XP_KEY_PREFIX}{chat_id}", 0)
    except Exception as e:
        logger.error(f"Ошибка сброса XP: {e}")

    await update.message.reply_text(
        "⚠️ <b>ОГОЛОШЕНО ТЕХНІЧНИЙ ДЕФОЛТ!</b>\n\n"
        "Всі борги списані. Ранги обнулені.\n"
        "Починаємо життя з чистого аркуша.\n\n"
        "⚡️ Потужність: <b>0</b>\n"
        "🍫 Ранг: <b>ПОРОХОБОТИ</b>",
        parse_mode=ParseMode.HTML
    )

# --- ⭐️ НОВОЕ: ПОЛУЧЕНИЕ ID ГИФКИ ⭐️ ---
async def get_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если сообщение содержит анимацию, бот вернет ее ID
    if not update.message.animation:
        return
        
    file_id = update.message.animation.file_id
    
    # Отвечаем пользователю кодом, чтобы удобно было копировать
    await update.message.reply_text(
        f"🆔 <b>ID GIF:</b>\n<code>{file_id}</code>",
        parse_mode=ParseMode.HTML
    )

# --- ⭐️ ОБРАБОТЧИК СООБЩЕНИЙ + РАНДОМАЙЗЕР ⭐️ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    
    chat_id = str(update.message.chat_id) 
    
    # 1. ЛОГИКА РАНГОВ
    try:
        new_xp = redis.incr(f"{XP_KEY_PREFIX}{chat_id}")
        if new_xp in RANK_THRESHOLDS:
            config = RANK_THRESHOLDS[new_xp]
            await context.bot.send_message(chat_id=chat_id, text=config["msg"], parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка XP: {e}")

    # 2. ЛОГИКА ИГРЫ (+/-)
    if not update.message.text: return
    message_text = update.message.text.strip()

    match = re.search(r'([+-])\s*(\d+)', message_text)
    if match:
        operator = match.group(1)
        try: 
            value = int(match.group(2))
        except ValueError: 
            return

        # --- 🔥 НАЧАЛО РАНДОМАЙЗЕРА 🔥 ---
        bonus_text = ""
        
        if operator == '+':
            chance = random.random()
            
            if chance > 0.75 and chance <= 0.80: # 5%
                value = value * 2
                bonus_text = "\n🇺🇸 <b>ПЕРЕМОГА! МВФ дав транш! (x2)</b>"
                
            elif chance > 0.80 and chance <= 0.85: # 5%
                value = value + 500
                bonus_text = "\n💰 <b>ПЕРЕМОГА! Знайшов заначку Януковича! (+500)</b>"
                
            elif chance > 0.85 and chance <= 0.90: # 5%
                value = max(1, int(value / 2))
                bonus_text = "\n🤡 <b>ЗРАДА! Половина пішла на відкат... (/2)</b>"
                
            elif chance > 0.90 and chance <= 0.95: # 5%
                value = 0
                bonus_text = "\n👮‍♂️ <b>ЗРАДА! Гроші заблоковані фінмоніторингом! (0)</b>"
                
            elif chance > 0.95: # 5%
                value = -value
                bonus_text = "\n🔄 <b>ЗРАДА! Ти переплутав кнопки! (Інверсія)</b>"
        # --- КОНЕЦ РАНДОМАЙЗЕРА ---

        current_score = load_scores(chat_id) 
        new_score = current_score + value
        
        if operator == '+': 
            gif_id = random.choice(POSITIVE_GIF_IDS)
        else: 
            new_score = current_score - value
            gif_id = random.choice(NEGATIVE_GIF_IDS)

        save_scores(chat_id, new_score) 

        reply_text = f"🏆 <b>Рахунок потужності:</b> <code>{new_score}</code>{bonus_text}"

        try:
            await update.message.reply_animation(
                animation=gif_id,
                caption=reply_text,
                parse_mode=ParseMode.HTML
            )
        except Exception:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

# --- ЗАПУСК ---
def main_bot():
    job_queue = JobQueue()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()
    UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
    
    # Таймеры
    application.job_queue.run_daily(send_evening_message, time=datetime.time(20, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    application.job_queue.run_daily(send_morning_message, time=datetime.time(8, 0, tzinfo=UKRAINE_TZ), days=(0, 1, 2, 3, 4, 5, 6))

    # Команды
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
    # ⭐️ Хендлер для ловли гифок (чтобы узнать ID)
    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    
    # Хендлер для текста (Игра и Ранги)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("Бот 'ПОТУЖНИЙ' (FINAL PRODUCTION) запущен...")
    application.run_polling()

if __name__ == '__main__':
    if not TOKEN or not UPSTASH_URL:
        print("КРИТИЧЕСКАЯ ОШИБКА: Нет переменных окружения!")
    else:
        server_thread = Thread(target=run_web_server)
        server_thread.daemon = True 
        server_thread.start()
        main_bot()
