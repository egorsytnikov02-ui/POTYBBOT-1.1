def escape_html(value):
    return html.escape(str(value or ""), quote=True)


def format_uah(amount_minor_units):
    """Steam передає суми у найменших одиницях валюти."""
    amount = int(amount_minor_units) / 100
    formatted = f"{amount:,.0f}".replace(",", " ")
    return f"{formatted} ₴"


async def safe_send(context, chat_id, text=None, animation=None, photo=None):
    """Надсилає повідомлення, але не видаляє рахунок чату через помилку."""
    try:
        if animation:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=animation,
                caption=text,
                parse_mode=ParseMode.HTML
            )
        elif photo:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            except BadRequest:
                # Якщо Telegram не зміг завантажити фото або підпис —
                # спробуємо надіслати дайджест звичайним повідомленням.
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
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
                photo=photo
            )
        except Exception:
            logger.exception("Не вдалося перенести дані чату після міграції.")

    except Forbidden:
        # Бот більше не має доступу до чату. Рахунок не видаляємо.
        logger.info("Бот не має доступу до чату %s.", chat_id)

    except Exception:
        logger.exception("Не вдалося надіслати повідомлення в чат %s.", chat_id)


def _fetch_json(url, params=None):
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def compile_digest():
    """Формує дайджест зі знижками Steam і роздачами Epic."""
    digest_parts = []
    steam_savings_total = 0

    # --- Steam ---
    try:
        data = _fetch_json(STEAM_FEATURED_URL)
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
                details = _fetch_json(
                    STEAM_DETAILS_URL,
                    params={"appids": game_id, "cc": "UA", "l": "ukrainian"}
                )

                game_result = details.get(game_id, {})
                if not game_result.get("success"):
                    continue

                game = game_result.get("data", {})
                price = game.get("price_overview", {})

                discount = int(price.get("discount_percent", 0))
                if discount <= 0:
                    continue

                initial = int(price.get("initial", 0))
                final = int(price.get("final", 0))
                saving = max(0, initial - final)

                seen_key = f"seen_steam_{game_id}"
                was_shown = redis.get(seen_key)

                candidates.append({
                    "id": game_id,
                    "name": game.get("name", item.get("name", "Невідома гра")),
                    "url": f"https://store.steampowered.com/app/{game_id}/",
                    "discount": discount,
                    "initial": initial,
                    "final": final,
                    "saving": saving,
                    "final_formatted": price.get(
                        "final_formatted",
                        format_uah(final)
                    ),
                    "initial_formatted": price.get(
                        "initial_formatted",
                        format_uah(initial)
                    ),
                    "seen": bool(was_shown),
                })

            except Exception:
                logger.exception(
                    "Не вдалося отримати дані Steam для гри %s.", game_id
                )

        # Спочатку вибираємо ще не показані ігри.
        unseen = [game for game in candidates if not game["seen"]]
        pool = unseen if unseen else candidates

        # Найбільша знижка — вище; за однакової знижки — більша економія.
        pool.sort(
            key=lambda game: (game["discount"], game["saving"]),
            reverse=True
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
                    f"• <a href=\"{url}\">{name}</a>\n"
                    f"  <s>{old_price}</s> → <b>{new_price}</b> "
                    f"(−{game['discount']}%)"
                )

                steam_savings_total += game["saving"]

                # Позначаємо показаною лише гру, що потрапила до дайджесту.
                redis.setex(
                    f"seen_steam_{game['id']}",
                    SEEN_GAME_TTL,
                    "1"
                )

            digest_parts.append("\n".join(steam_lines))

    except Exception:
        logger.exception("Помилка під час отримання знижок Steam.")

    # --- Epic Games Store ---
    try:
        epic_data = _fetch_json(EPIC_API_URL)

        if isinstance(epic_data, list) and epic_data:
            epic_lines = ["🎁 <b>Безкоштовно в Epic Games:</b>"]

            # Показуємо до двох актуальних роздач.
            for game in epic_data[:2]:
                title = escape_html(game.get("title", "Безкоштовна гра"))
                link = escape_html(game.get("open_giveaway_url", ""))
                end_date = game.get("end_date")

                line = f"• <a href=\"{link}\">{title}</a>"

                if end_date and str(end_date).upper() != "N/A":
                    line += f"\n  ⏳ До: <b>{escape_html(end_date)}</b>"

                epic_lines.append(line)

            digest_parts.append("\n".join(epic_lines))

    except Exception:
        logger.exception("Помилка під час отримання роздач Epic Games.")

    if not digest_parts:
        return None, None

    header = "🎮 <b>Ігровий дайджест</b>\n\n"
    footer = "\n\n<i>Гарної гри! Не забудь залишити трохи грошей на їжу.</i>"

    if steam_savings_total > 0:
        savings_text = (
            "\n\n💸 Якщо придбати всі показані ігри Steam, "
            f"можна заощадити приблизно "
            f"<b>{format_uah(steam_savings_total)}</b>."
        )
    else:
        savings_text = ""

    full_text = header + "\n\n".join(digest_parts) + savings_text + footer
    return full_text, DIGEST_IMAGE_URL


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Формую ігровий дайджест.")

    # Запити Steam/Epic синхронні, тому запускаємо їх окремо,
    # щоб не затримувати обробку повідомлень бота.
    text, image_url = await asyncio.to_thread(compile_digest)

    if not text:
        logger.info("Сьогодні для дайджесту немає пропозицій.")
        return

    all_chats = redis.hgetall(SCORES_KEY)
    if not all_chats:
        return

    for chat_id in all_chats.keys():
        await safe_send(context, chat_id, text=text, photo=image_url)
    
