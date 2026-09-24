import asyncio
import datetime
import html
import logging
import os
import random
import re
from threading import Thread

import pytz
import requests
from flask import Flask
from waitress import serve
from upstash_redis import Redis

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, ChatMigrated, Forbidden
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# --- 1. Логирование ---
class TokenFilter(logging.Filter):
    def filter(self, record):
        token = os.environ.get("TOKEN")
        return not (token and token in record.getMessage())


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

for handler in logging.root.handlers:
    handler.addFilter(TokenFilter())

logger = logging.getLogger(__name__)


# --- 2. Переменные окружения ---
TOKEN = os.environ.get("TOKEN")
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")


# --- 3. Redis ---
if not UPSTASH_URL or not UPSTASH_TOKEN:
    raise RuntimeError(
        "Задайте UPSTASH_REDIS_REST_URL і UPSTASH_REDIS_REST_TOKEN "
        "у змінних середовища."
    )

try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger.info("Підключення до Redis налаштовано.")
except Exception:
    logger.exception("Не вдалося підключитися до Redis.")
    raise


# --- 4. Вебсервер для Render ---
app = Flask(__name__)


@app.route("/")
def home():
    return "Бот «ПОТУЖНИЙ» працює!"


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    serve(app, host="0.0.0.0", port=port)


# --- 5. Налаштування ---
SCORES_KEY = "potuzhniy_scores"
USERS_KEY = "potuzhniy_unique_users"

STEAM_FEATURED_URL = (
    "https://store.steampowered.com/api/featuredcategories"
    "?CC=UA&l=ukrainian"
)
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
EPIC_API_URL = (
    "https://www.gamerpower.com/api/giveaways"
    "?platform=epic-games-store&type=game&sort-by=date"
)

# Не показувати ту саму гру повторно протягом трьох днів
SEEN_GAME_TTL = 60 * 60 * 24 * 3

STEAM_CANDIDATES_LIMIT = 15
STEAM_DIGEST_GAMES_LIMIT = 3

DIGEST_IMAGE_URL = (
    "https://i.redd.it/the-origin-of-dog-closing-eyes-meme-yakuza-3-v0-"
    "txfwdc8oi2ve1.jpg?width=567&format=pjpg&auto=webp&"
    "s=0b51ed14c2acfbeed5e54329f158187a8e881e32"
)

BOT_REPLY_PHRASES = [
    "Іди своєю дорогою, сталкере. Тут немає артефактів для тебе.",
    "Ще одне слово — і я тебе в «Холодець» кину.",
    "Не фоніть. Мій лічильник Гейгера тріщить від вашого крінжу.",
    "Ти що, безсмертний? Збереження давно робив?",
    "НЕ ЧІПАЙ МЕНЕ, ШМАТОК М'ЯСА!",
    "Ти так сміливо пишеш... А дані в «Резерв+» оновив?",
    "Громадянине, пред'явіть військовий квиток або штрихкод!",
    "Не бачу твоєї електронної декларації. Розмову завершено.",
    "Запит відхилено. Ти забув додати хабар до повідомлення.",
    "Зараз зателефоную в ДТЕК — і тебе відключать поза чергою.",
    "У нас дефіцит потужності в енергосистемі. Не витрачай мої байти дарма.",
    "МВФ не схвалює твою поведінку. Транш скасовано.",
    "Вийди звідси, розбійнику! Ти мене чуєш?",
    "Я тобі нічого не винен. Я ж не лох якийсь.",
    "Це провокація! Скаржитимусь в ООН. Хоча їм, мабуть, байдуже.",
]

POSITIVE_GIF_IDS = [
    "CgACAgIAAyEFAATIovxHAAIDDWkcMy0m8C5AL5UW9vaBZ0JIUHhsAAJkhwACYjrZSAOnzOZuDDU6NgQ",
    "CgACAgQAAyEFAATIovxHAAIDEmkcMy1wQjRBAluj_AXzdQPqkVd0AALZCwACRO1JUBTOazJVNz4lNgQ",
    "CgACAgQAAyEFAATIovxHAAIDE2kcMy3Sq2SRn1idBKYth4GYxSLmAAKBBwAC433cUKZnfhyAKjuVNgQ",
    "CgACAgQAAyEFAATIovxHAAIDFGkcMy2jOW2jpAzJYKvMAcUf820uAAIVBwACME5MUQkcFAABdz9BzjYE",
    "CgACAgQAAyEFAATIovxHAAIDFmkcMy1RSw8Mc2i_WLjrhZY7r62aAAI3BwACKbQMUI-7MMr1sGU5NgQ",
    "CgACAgQAAyEFAATIovxHAAIDFWkcMy3sBmzcsvunOSvq8CqTFeZJAAIoBgACFs_0UWK1EYRe_OceNgQ",
    "CgACAgIAAyEFAATIovxHAAICSmkbZVhc1_Ff9ymU6mj8JzxqmDNXAAIRBwACGVY9Uo0EYWP8LfbBNgQ",
    "CgACAgQAAyEFAATIovxHAAIDGGkcMy1bYuToU-3pbu70GwSg3vFIAAIKBwACGAV1U1fbtsKLFSETNgQ",
    "CgACAgQAAyEFAATIovxHAAIDGWkcMy3E8mqcq9daCAngW1xWAjp7AAL9BgAC0HSMU9zF9CSFB2QjNgQ",
    "CgACAgQAAyEFAATIovxHAAIDGmkcMy3uElNklpmDgBeW35PgFEREAAL0BgACG0V1U0tBqgM4lfk_NgQ",
    "CgACAgQAAyEFAATIovxHAAIDEGkcMy1_JWbQ4AmY0H6iKRGZYOLgAAK5BgACwQ01UG834SxB23AlNgQ",
]

NEGATIVE_GIF_IDS = [
    "CgACAgIAAyEFAATIovxHAAIDDmkcMy2DYcJtlJTkU_ZN02iVPdRSAALIjAACA8jYSHQ4Pa-xroPQNgQ",
    "CgACAgQAAyEFAATIovxHAAIDEWkcMy1XvSbhxGnxdYsLRD6jTHpVAAL6BwACJxdNU_aOqAjhtOajNgQ",
    "CgACAgQAAyEFAATIovxHAAIDG2kcMy2xDXNvCKMmkpjFt9aULAahAAIyCAACixY1U7CC6tw4zC7KNgQ",
]

REPLY_TO_BOT_GIF_ID = (
    "CgACAgIAAyEFAATIovxHAAIBSmkbMaIuOb-D2BxGZdpSf03s1IDcAAJAgwACSL3ZSLtCpogi_5_INgQ"
)


# --- 6. Допоміжні функції ---
def load_scores(chat_id):
    try:
        score = redis.hget(SCORES_KEY, str(chat_id))
        return int(score) if score else 0
    except Exception:
        logger.exception("Не вдалося прочитати рахунок чату.")
        return 0


def save_scores(chat_id, new_score):
    try:
        redis.hset(SCORES_KEY, str(chat_id), str(new_score))
    except Exception:
        logger.exception("Не вдалося зберегти рахунок чату.")


def escape_html(value):
    return html.escape(str(value or ""), quote=True)


def format_uah(amount_minor_units):
    """Перетворює суму Steam із копійок на гривні."""
    amount = int(amount_minor_units) / 100
    formatted = f"{amount:,.0f}".replace(",", " ")
    return f"{formatted} ₴"


async def safe_send(context, chat_id, text=None, animation=None, photo=None):
    """Надсилає повідомлення і не видаляє рахунок через помилку."""
    try:
        if animation:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=animation,
                caption=text,
                parse_mode=ParseMode.HTML,
            )
        elif photo:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
            except BadRequest:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    except ChatMigrated as error:
        old_chat_id = str(chat_id)
        new_chat_id = str(error.new_chat_id)

        try:
            old_score = redis.hget(SCORES_KEY, old_chat_id)
            if old_score is not None:
                redis.hset(SCORES_KEY, new_chat_id, old_score)
            redis.hdel(SCORES_KEY, old_chat_id)

            await safe_send(
                context,
                new_chat_id,
                text=text,
                animation=animation,
                photo=photo,
            )
        except Exception:
            logger.exception("Не вдалося перенести дані чату.")

    except Forbidden:
        logger.info("Бот більше не має доступу до чату %s.", chat_id)

    except Exception:
        logger.exception("Не вдалося надіслати повідомлення в чат %s.", chat_id)


# --- 7. Формування дайджесту ---
def fetch_json(url, params=None):
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def compile_digest():
    digest_parts = []
    steam_savings_total = 0

    # Steam
    try:
        data = fetch_json(STEAM_FEATURED_URL)
        specials = data.get("specials", {}).get("items", [])

        candidates = []
        checked_ids = set()

        for item in specials:
            if len(checked_ids) >= STEAM_CANDIDATES_LIMIT:
                break

            game_id = str(item.get("id", ""))
            if not game_id or game_id in checked_ids:
                continue

            checked_ids.add(game_id)

            try:
                details = fetch_json(
                    STEAM_DETAILS_URL,
                    params={
                        "appids": game_id,
                        "cc": "UA",
                        "l": "ukrainian",
                    },
                )

                result = details.get(game_id, {})
                if not result.get("success"):
                    continue

                game = result.get("data", {})
                price = game.get("price_overview", {})

                discount = int(price.get("discount_percent", 0))
                if discount <= 0:
                    continue

                initial = int(price.get("initial", 0))
                final = int(price.get("final", 0))

                candidates.append(
                    {
                        "id": game_id,
                        "name": game.get("name", item.get("name", "Невідома гра")),
                        "url": f"https://store.steampowered.com/app/{game_id}/",
                        "discount": discount,
                        "saving": max(0, initial - final),
                        "initial_formatted": price.get(
                            "initial_formatted",
                            format_uah(initial),
                        ),
                        "final_formatted": price.get(
                            "final_formatted",
                            format_uah(final),
                        ),
                        "seen": bool(redis.get(f"seen_steam_{game_id}")),
                    }
                )

            except Exception:
                logger.exception(
                    "Не вдалося отримати дані Steam для гри %s.",
                    game_id,
                )

        # Спершу показуємо ігри, яких не було в недавніх дайджестах.
        unseen = [game for game in candidates if not game["seen"]]
        pool = unseen if unseen else candidates

        # Сортуємо за розміром знижки, потім — за сумою економії.
        pool.sort(
            key=lambda game: (game["discount"], game["saving"]),
            reverse=True,
        )

        selected = pool[:STEAM_DIGEST_GAMES_LIMIT]

        if selected:
            steam_lines = ["📉 <b>Найвигідніші знижки Steam:</b>"]

            for game in selected:
                name = escape_html(game["name"])
                url = escape_html(game["url"])
                old_price = escape_html(game["initial_formatted"])
                new_price = escape_html(game["final_formatted"])

                steam_lines.append(
                    f'• <a href="{url}">{name}</a>\n'
                    f"  <s>{old_price}</s> → <b>{new_price}</b> "
                    f"(−{game['discount']}%)"
                )

                steam_savings_total += game["saving"]

                # Позначаємо лише ті ігри, які справді потрапили в дайджест.
                redis.setex(
                    f"seen_steam_{game['id']}",
                    SEEN_GAME_TTL,
                    "1",
                )

            digest_parts.append("\n".join(steam_lines))

    except Exception:
        logger.exception("Не вдалося отримати знижки Steam.")

    # Epic Games Store
    try:
        epic_data = fetch_json(EPIC_API_URL)

        if isinstance(epic_data, list) and epic_data:
            epic_lines = ["🎁 <b>Безкоштовно в Epic Games:</b>"]

            for game in epic_data[:2]:
                title = escape_html(game.get("title", "Безкоштовна гра"))
                link = escape_html(game.get("open_giveaway_url", ""))
                end_date = game.get("end_date")

                line = f'• <a href="{link}">{title}</a>'

                if end_date and str(end_date).upper() != "N/A":
                    line += f"\n  ⏳ До: <b>{escape_html(end_date)}</b>"

                epic_lines.append(line)

            digest_parts.append("\n".join(epic_lines))

    except Exception:
        logger.exception("Не вдалося отримати роздачі Epic Games.")

    if not digest_parts:
        return None, None

    text = "🎮 <b>Ігровий дайджест</b>\n\n"
    text += "\n\n".join(digest_parts)

    if steam_savings_total > 0:
        text += (
            "\n\n💸 Якщо придбати всі показані ігри Steam, "
            f"можна заощадити приблизно "
            f"<b>{format_uah(steam_savings_total)}</b>."
        )

    text += "\n\n<i>Гарної гри! Залиш трохи грошей на їжу.</i>"

    return text, DIGEST_IMAGE_URL


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Формую ігровий дайджест.")

    # Запити до Steam та Epic синхронні — виконуємо їх в окремому потоці.
    text, image_url = await asyncio.to_thread(compile_digest)

    if not text:
        logger.info("Для сьогоднішнього дайджесту немає пропозицій.")
        return

    try:
        all_chats = redis.hgetall(SCORES_KEY)
    except Exception:
        logger.exception("Не вдалося отримати список чатів із Redis.")
        return

    if not all_chats:
        return

    for chat_id in all_chats.keys():
        await safe_send(context, chat_id, text=text, photo=image_url)


# --- 8. Команди ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    score = load_scores(chat_id)

    await update.message.reply_text(
        f"📊 <b>Потужність спільноти:</b> <code>{score}</code>",
        parse_mode=ParseMode.HTML,
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("🚫 Тільки для адміністраторів!")
            return
    except Exception:
        return

    try:
        total_chats = redis.hlen(SCORES_KEY)
        total_users = redis.scard(USERS_KEY)

        text = (
            "🤖 <b>СИСТЕМНА ІНФОРМАЦІЯ</b>\n\n"
            f"📂 <b>Активних чатів:</b> <code>{total_chats}</code>\n"
            f"👤 <b>Користувачів:</b> <code>{total_users}</code>"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception:
        logger.exception("Не вдалося отримати статистику.")
        await update.message.reply_text(
            "❌ Не вдалося отримати статистику.",
        )


async def steam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            return
    except Exception:
        return

    await update.message.reply_text(
        "📰 <b>Формую тестовий дайджест...</b>",
        parse_mode=ParseMode.HTML,
    )

    text, image_url = await asyncio.to_thread(compile_digest)

    if not text:
        await update.message.reply_text(
            "❌ У дайджесті поки немає пропозицій або API недоступні."
        )
        return

    try:
        await update.message.reply_photo(
            photo=image_url,
            caption=text,
            parse_mode=ParseMode.HTML,
        )
    except BadRequest:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    try:
        member = await chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text(
                "❌ Цю команду можуть виконувати лише адміністратори."
            )
            return
    except Exception:
        return

    save_scores(str(chat.id), 0)

    await update.message.reply_text(
        "⚠️ <b>ОГОЛОШЕНО ТЕХНІЧНИЙ ДЕФОЛТ!</b>\n\n"
        "⚡️ Потужність: <b>0</b>",
        parse_mode=ParseMode.HTML,
    )


async def gif_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        member = await update.effective_chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            return
    except Exception:
        return

    # Налаштування зберігається окремо для кожного чату.
    chat_id = update.effective_chat.id
    context.chat_data["gif_mode"] = not context.chat_data.get("gif_mode", False)

    state = (
        "✅ <b>УВІМКНЕНО</b>"
        if context.chat_data["gif_mode"]
        else "🛑 <b>ВИМКНЕНО</b>"
    )

    await update.message.reply_text(
        f"🕵️‍♂️ Режим збирання ID гіфок: {state}",
        parse_mode=ParseMode.HTML,
    )


async def get_gif_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        context.chat_data.get("gif_mode", False)
        and update.message
        and update.message.animation
    ):
        await update.message.reply_text(
            "🆔 <b>ID гіфки:</b>\n"
            f"<code>{update.message.animation.file_id}</code>",
            parse_mode=ParseMode.HTML,
        )


# --- 9. Обробка звичайних повідомлень ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message
    chat_id = str(message.chat_id)

    if update.effective_user:
        try:
            redis.sadd(USERS_KEY, update.effective_user.id)
        except Exception:
            logger.exception("Не вдалося оновити список користувачів.")

    if (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == context.bot.id
    ):
        try:
            await message.reply_animation(
                animation=REPLY_TO_BOT_GIF_ID,
                caption=random.choice(BOT_REPLY_PHRASES),
            )
        except Exception:
            logger.exception("Не вдалося надіслати гіфку-відповідь.")

    if not message.text:
        return

    match = re.search(r"(?:^|\s)([+-])\s*(\d+)", message.text.strip())
    if not match:
        return

    operator = match.group(1)

    try:
        value = int(match.group(2))
    except ValueError:
        return

    if value == 300:
        await message.reply_text(
            "🚜 <b>Я саме на тракторі. Зараз приїду — і буде бій.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    if value > 10:
        await message.reply_text(
            "🛑 <b>А чи не забагато хочеш?</b>\n"
            "МВФ стільки грошей не виділив. "
            "Ліміт — 10 очок.",
            parse_mode=ParseMode.HTML,
        )
        return

    current_score = load_scores(chat_id)
    delta = value if operator == "+" else -value
    new_score = current_score + delta
    save_scores(chat_id, new_score)

    gif_id = random.choice(
        POSITIVE_GIF_IDS if delta >= 0 else NEGATIVE_GIF_IDS
    )

    caption = (
        "🏆 <b>Рахунок потужності:</b> "
        f"<code>{new_score}</code>"
    )

    try:
        await message.reply_animation(
            animation=gif_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
        )


# --- 10. Запуск ---
def main_bot():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("gifmode", gif_mode_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("steam", steam_command))

    application.add_handler(MessageHandler(filters.ANIMATION, get_gif_id))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_message)
    )

    kyiv_timezone = pytz.timezone("Europe/Kyiv")

    application.job_queue.run_daily(
        send_daily_digest,
        time=datetime.time(10, 0, tzinfo=kyiv_timezone),
        days=tuple(range(7)),
    )

    logger.info("Бот запущено.")
    application.run_polling()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Задайте змінну середовища TOKEN.")

    server_thread = Thread(target=run_web_server, daemon=True)
    server_thread.start()

    main_bot()
