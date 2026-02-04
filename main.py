import logging
import os
import re
import datetime
import pytz
import random
import requests

from threading import Thread
from flask import Flask
from waitress import serve

from upstash_redis import Redis

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, ChatMigrated

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
USERS_KEY = "potuzhniy_unique_users"

# Настройки для Дайджеста
STEAM_FEATURED_URL = "https://store.steampowered.com/api/featuredcategories?CC=UA&l=ukrainian"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
EPIC_API_URL = "https://www.gamerpower.com/api/giveaways?platform=epic-games-store&type=game&sort-by=date"
SEEN_GAME_TTL = 60 * 60 * 24 * 7 

# 🔥 ВСТАВЬ СЮДА ССЫЛКУ НА СВОЮ КАРТИНКУ 🔥
# Это может быть URL (https://...) или File_ID телеграма
DIGEST_IMAGE_URL = "https://i.redd.it/the-origin-of-dog-closing-eyes-meme-yakuza-3-v0-txfwdc8oi2ve1.jpg?width=567&format=pjpg&auto=webp&s=0b51ed14c2acfbeed5e54329f158187a8e881e32" 

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

async def safe_send(context, chat_id, text=None, animation=None, photo=None):
    try:
        if animation:
            await context.bot.send_animation(chat_id=chat_id, animation=animation, caption=text, parse_mode=ParseMode.HTML)
        elif photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except ChatMigrated as e:
        new_id = str(e.new_chat_id)
        old_score = redis.hget(SCORES_KEY, chat_id)
        if old_score: redis.hset(SCORES_KEY, new_id, old_score)
        redis.hdel(SCORES_KEY, chat_id)
        try:
            if animation: await context.bot.send_animation(chat_id=new_id, animation=animation, caption=text, parse_mode=ParseMode.HTML)
            elif photo: await context.bot.send_photo(chat_id=new_id, photo=photo, caption=text, parse_mode=ParseMode.HTML)
            else: await context.bot.send_message(chat_id=new_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception: pass
    except (BadRequest, Forbidden):
        redis.hdel(SCORES_KEY, chat_id)
    except Exception: pass

# --- 7. ЛОГИКА ДАЙДЖЕСТА (v4: Статичная картинка) ---
def compile_digest():
    digest_parts = []
    has_content = False
    
    # 1. STEAM
    try:
        # Этап 1: Список
        response = requests.get(STEAM_FEATURED_URL, timeout=10)
        data = response.json()
        specials = data.get('specials', {}).get('items', [])
        found_games = []
        
        for item in specials:
            if len(found_games) >= 3: break 
            
            game_id = str(item.get('id'))
            seen_key = f"seen_steam_{game_id}"
            
            if redis.get(seen_key): continue 
            
            # Этап 2: Детали
            try:
                details_resp = requests.get(f"{STEAM_DETAILS_URL}?appids={game_id}&cc=UA", timeout=5)
                details_data = details_resp.json()
                
                if not details_data.get(game_id, {}).get('success'): continue
                
                game_data = details_data[game_id]['data']
                price_overview = game_data.get('price_overview', {})
                
                if not price_overview.get('discount_percent'): continue

                name = game_data['name']
                discount = price_overview['discount_percent']
                final_price_formatted = price_overview['final_formatted']
                link = f"https://store.steampowered.com/app/{game_id}"
                
                found_games.append(f"• <a href='{link}'>{name}</a>: <b>-{discount}%</b> ({final_price_formatted})")
                redis.setex(seen_key, SEEN_GAME_TTL, "1")
                
            except Exception as e:
                logger.error(f"Error getting details for game {game_id}: {e}")
                continue

        if found_games:
            steam_text = "📉 <b>Топ знижок у Steam:</b>\n" + "\n".join(found_games)
            digest_parts.append(steam_text)
            has_content = True

    except Exception as e:
        logger.error(f"Steam Digest Error: {e}")

    # 2. EPIC GAMES
    try:
        response = requests.get(EPIC_API_URL, timeout=10)
        data = response.json()
        if data:
            game = data[0]
            title = game.get('title')
            link = game.get('open_giveaway_url')
            epic_text = f"🎁 <b>Роздача Epic Games:</b>\n• <a href='{link}'>{title}</a> (Безкоштовно)"
            digest_parts.append(epic_text)
            has_content = True

    except Exception as e:
        logger.error(f"Epic Digest Error: {e}")

    if not has_content:
        return None, None

    header = "🎮 <b>Геймерський дайджест</b>\n\n"
    footer = "\n\n<i>Гарної гри!</i>"
    full_text = header + "\n\n".join(digest_parts) + footer
    
    # Возвращаем Текст и ТУ САМУЮ КАРТИНКУ
    return full_text, DIGEST_IMAGE_URL

async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE):
    logger.info("📰 Формирование дайджеста...")
    text, image_url = compile_digest()
    
    if not text:
        logger.info("Дайджест пуст.")
        return

    all_chats = redis.hgetall(SCORES_KEY)
    if not all_chats: return

    for chat_id in all_chats.keys():
        await safe_send(context, chat_id, text=text, photo=image_url)

# --- 8. КОМАНДЫ ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    score = load_scores(chat_id)
    await update.message.reply_text(f"📊 <b>Потужність спільноти:</b> <code>{score}</code>", parse_mode=ParseMode.HTML)

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
        total_users = redis.scard(USERS_KEY)
        text = f"🤖 <b>СИСТЕМНА ІНФОРМАЦІЯ</b>\n\n📂 <b>Активних чатів:</b> <code>{total_chats}</code>\n👤 <b>Користувачів:</b> <code>{total_users}</code>"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# 🔥 КОМАНДА /steam 🔥
async def steam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            return
    except Exception: return

    await update.message.reply_text("📰 <b>Формую тестовий дайджест...</b>", parse_mode=ParseMode.HTML)
    
    text, image_url = compile_digest()
    
    if text:
        if image_url:
             await update.message.reply_photo(photo=image_url, caption=text, parse_mode=ParseMode.HTML)
        else:
             await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        await update.message.reply_text("❌ Дайджест пустий (або помилка API).", parse_mode=ParseMode.HTML)

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

# --- 9. ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat_id = str(update.message.chat_id) 
    
    if update.effective_user:
        try: redis.sadd(USERS_KEY, update.effective_user.id)
        except Exception: pass

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

# --- 10. ЗАПУСК ---
def main_bot():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("gifmode", gif_mode_command))
    application.add_handler(CommandHandler("admin", admin_command)) 
    application.add_handler(CommandHandler("steam", steam_command))
    
    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    tz = pytz.timezone('Europe/Kyiv')
    
    # 📰 Ежедневный дайджест в 10:00 утра
    application.job_queue.run_daily(send_daily_digest, time=datetime.time(10, 0, tzinfo=tz), days=(0, 1, 2, 3, 4, 5, 6))

    print("🚀 Бот запущен (Дайджест v4: Статичное фото)...")
    application.run_polling()

if __name__ == '__main__':
    if not TOKEN or not UPSTASH_URL:
        print("❌ ОШИБКА: Нет переменных окружения!")
    else:
        server_thread = Thread(target=run_web_server)
        server_thread.daemon = True 
        server_thread.start()
        main_bot()
