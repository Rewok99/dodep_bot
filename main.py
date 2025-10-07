import json
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import asyncio

# === НАСТРОЙКИ ===
TOKEN = "8322042811:AAHzdQ-XFQvopNDSWXqe8zjeuvUjO0FH0ug"
DATA_FILE = Path("data.json")
CHANNEL_USERNAME = "@rewokayo"
START_POINTS = 1000
BONUS_POINTS = 1000
BONUS_COOLDOWN_MINUTES = 60

# === ГЛОБАЛЬНЫЕ ДАННЫЕ ===
usernames_cache = {}
duels = {}  # chat_id -> {"initiator_id": ..., "bet": ..., "message_id": ...}

# === ЗАГРУЗКА / СОХРАНЕНИЕ ===
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        users_data = json.load(f)
else:
    users_data = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

def get_username_map():
    return users_data.setdefault("usernames", {})

def save_username(user, chat_id=None):
    if user.username:
        uname = user.username.lower()
        usernames_cache[uname] = user.id
        get_username_map()[uname] = user.id

    if chat_id:
        chat_data = users_data.setdefault(str(chat_id), {})
        points_data = chat_data.setdefault("points", {})
        if str(user.id) not in points_data:
            points_data[str(user.id)] = START_POINTS
    save_data()

def load_username_cache():
    usernames = users_data.get("usernames", {})
    usernames_cache.update(usernames)

load_username_cache()

# === ОЧКИ ===
def get_user_points(chat_id, user_id):
    return users_data.get(str(chat_id), {}).get("points", {}).get(str(user_id), START_POINTS)

def update_user_points(chat_id, user_id, points):
    chat_data = users_data.setdefault(str(chat_id), {})
    points_data = chat_data.setdefault("points", {})
    points_data[str(user_id)] = get_user_points(chat_id, user_id) + points
    save_data()

# === БОНУСЫ ===
def get_last_bonus_time(chat_id, user_id):
    return users_data.get(str(chat_id), {}).get("bonus_time", {}).get(str(user_id))

def set_last_bonus_time(chat_id, user_id):
    chat_data = users_data.setdefault(str(chat_id), {})
    bonus_data = chat_data.setdefault("bonus_time", {})
    bonus_data[str(user_id)] = datetime.now().isoformat()
    save_data()

# === ВСПОМОГАТЕЛЬНЫЕ ===
def get_username_by_id(user_id):
    for uname, uid in usernames_cache.items():
        if uid == user_id:
            return uname
    return "неизвестный"

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Команды бота:\n"
        "💰 !баланс — показать баланс\n"
        "🎰 !дэп <ставка> — сыграть в слот (например: !дэп 100)\n"
        "🎁 !бонус — получить бонус (раз в час)\n"
        "💸 !дать @логин 100 — перевести очки другому пользователю\n"
        "⚔️ !дуэль <ставка> — вызвать кого-то на дуэль!"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)
    points = get_user_points(chat_id, user.id)
    await update.message.reply_text(f"У тебя {points} очков 🎯")

async def dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)
    points = get_user_points(chat_id, user.id)

    args = update.message.text.strip().split()
    if len(args) > 1:
        try:
            bet = int(args[1])
        except ValueError:
            await update.message.reply_text("⚠️ Укажи число после !дэп, например: !дэп 100")
            return
    else:
        bet = 10

    if bet <= 0:
        await update.message.reply_text("😒 Ставка должна быть больше нуля.")
        return

    if points < bet:
        await update.message.reply_text(f"Недостаточно очков для ставки {bet} 💸. Баланс: {points}")
        return

    update_user_points(chat_id, user.id, -bet)
    sent = await update.message.reply_dice(emoji="🎰")
    await asyncio.sleep(2)
    dice_value = sent.dice.value

    multiplier = 0
    if dice_value in [1, 22, 43]:
        multiplier = 10
    elif dice_value == 64:
        multiplier = 100
    elif dice_value in [16, 32, 48]:
        multiplier = 5

    if multiplier > 0:
        reward = bet * multiplier
        update_user_points(chat_id, user.id, reward)
        await update.message.reply_text(
            f"🎉 Занос! Множитель ×{multiplier}, выигрыш {reward} очков!\n"
            f"Текущий баланс: {get_user_points(chat_id, user.id)}"
        )
    else:
        await update.message.reply_text(
            f"🎰 Не повезло... Ты проиграл {bet} очков.\n"
            f"Текущий баланс: {get_user_points(chat_id, user.id)}"
        )

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)

    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user.id)
        if member.status in ["left", "kicked"]:
            await update.message.reply_text(
                f"❌ Ты не подписан на канал {CHANNEL_USERNAME}. Подпишись, чтобы получить бонус!"
            )
            return
    except Exception as e:
        await update.message.reply_text(
            "❌ Не удалось проверить подписку. Убедись, что бот является админом канала."
        )
        print("Ошибка проверки подписки:", e)
        return

    last_bonus_time = get_last_bonus_time(chat_id, user.id)
    if last_bonus_time:
        last_time = datetime.fromisoformat(last_bonus_time)
        if datetime.now() - last_time < timedelta(minutes=BONUS_COOLDOWN_MINUTES):
            remaining = timedelta(minutes=BONUS_COOLDOWN_MINUTES) - (datetime.now() - last_time)
            minutes_left = int(remaining.total_seconds() // 60)
            seconds_left = int(remaining.total_seconds() % 60)
            await update.message.reply_text(
                f"⏳ Бонус можно получить через {minutes_left} мин {seconds_left} сек."
            )
            return

    update_user_points(chat_id, user.id, BONUS_POINTS)
    set_last_bonus_time(chat_id, user.id)
    await update.message.reply_text(
        f"🎁 Бонус начислен! +{BONUS_POINTS} очков.\n"
        f"Текущий баланс: {get_user_points(chat_id, user.id)}"
    )

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)

    args = update.message.text.strip().split()
    if len(args) < 3:
        await update.message.reply_text("⚠️ Формат: !дать @логин количество")
        return

    username = args[1].lstrip("@").lower()
    try:
        amount = int(args[2])
    except ValueError:
        await update.message.reply_text("⚠️ Укажи корректное число.")
        return

    if username not in usernames_cache:
        await update.message.reply_text("⚠️ Пользователь не найден.")
        return

    target_id = usernames_cache[username]
    sender_points = get_user_points(chat_id, user.id)
    if amount > sender_points:
        await update.message.reply_text(f"⚠️ Недостаточно очков. Баланс: {sender_points}")
        return

    update_user_points(chat_id, user.id, -amount)
    update_user_points(chat_id, target_id, amount)
    await update.message.reply_text(f"💸 Ты передал {amount} очков @{username} ✅")

# === ДУЭЛЬ ===
async def duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)

    args = update.message.text.strip().split()
    if len(args) < 2:
        await update.message.reply_text("⚔️ Формат: !дуэль ставка (например: !дуэль 200)")
        return

    try:
        bet = int(args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Укажи корректное число для ставки.")
        return

    if bet <= 0:
        await update.message.reply_text("😒 Ставка должна быть больше нуля.")
        return

    points = get_user_points(chat_id, user.id)
    if points < bet:
        await update.message.reply_text(f"💸 У тебя нет {bet} очков для дуэли. Баланс: {points}")
        return

    if chat_id in duels:
        await update.message.reply_text("⚠️ В этом чате уже есть активная дуэль.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Принять дуэль", callback_data=f"accept_duel:{chat_id}")]
    ])
    sent = await update.message.reply_text(
        f"💥 @{user.username} вызывает на дуэль на {bet} очков!\nКто осмелится принять вызов?",
        reply_markup=keyboard
    )

    duels[chat_id] = {"initiator_id": user.id, "bet": bet, "message_id": sent.message_id}

async def accept_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    # Всегда сразу отвечаем Telegram'у, иначе кнопка "висит"
    await query.answer("Дуэль принята! ⚔️")

    if chat_id not in duels:
        await query.edit_message_text("❌ Дуэль уже не активна.")
        return

    duel = duels[chat_id]
    initiator_id = duel["initiator_id"]
    bet = duel["bet"]

    if user.id == initiator_id:
        await query.answer("Ты не можешь принять свою же дуэль.")
        return

    initiator_points = get_user_points(chat_id, initiator_id)
    acceptor_points = get_user_points(chat_id, user.id)

    if initiator_points < bet:
        await query.edit_message_text("⚠️ У инициатора недостаточно очков. Дуэль отменена.")
        duels.pop(chat_id, None)
        return

    if acceptor_points < bet:
        await query.edit_message_text("⚠️ У принимающего недостаточно очков. Дуэль отменена.")
        duels.pop(chat_id, None)
        return

    update_user_points(chat_id, initiator_id, -bet)
    update_user_points(chat_id, user.id, -bet)

    await query.edit_message_text(
        f"⚔️ Дуэль между @{get_username_by_id(initiator_id)} и @{user.username} началась!\n"
        f"Каждый поставил {bet} очков!"
    )

    sent1 = await context.bot.send_dice(chat_id, emoji="🎲")
    await asyncio.sleep(3)
    sent2 = await context.bot.send_dice(chat_id, emoji="🎲")
    roll1 = sent1.dice.value
    roll2 = sent2.dice.value
    await asyncio.sleep(3)

    if roll1 > roll2:
        winner_id = initiator_id
        winner_username = get_username_by_id(initiator_id)
    elif roll2 > roll1:
        winner_id = user.id
        winner_username = user.username
    else:
        update_user_points(chat_id, initiator_id, bet)
        update_user_points(chat_id, user.id, bet)
        await context.bot.send_message(chat_id, "🤝 Ничья! Очки возвращены обоим.")
        duels.pop(chat_id, None)
        return

    prize = bet * 2
    update_user_points(chat_id, winner_id, prize)

    await context.bot.send_message(
        chat_id,
        f"🏆 Победитель дуэли — @{winner_username}! Он забирает {prize} очков!\n"
        f"🎯 Баланс: {get_user_points(chat_id, winner_id)}"
    )

    duels.pop(chat_id, None)

# === УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ===
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    text = update.message.text.lower()
    if text.startswith("!баланс"):
        await balance(update, context)
    elif text.startswith("!дэп"):
        await dep(update, context)
    elif text.startswith("!бонус"):
        await bonus(update, context)
    elif text.startswith("!дать"):
        await give(update, context)
    elif text.startswith("!дуэль"):
        await duel(update, context)

# === ЗАПУСК ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    app.add_handler(CallbackQueryHandler(accept_duel, pattern=r"^accept_duel:"))
    print("Бот запущен...")
    app.run_polling(drop_pending_updates=True)
