import json
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

TOKEN = "8322042811:AAHzdQ-XFQvopNDSWXqe8zjeuvUjO0FH0ug"
DATA_FILE = Path("data.json")
CHANNEL_USERNAME = "@rewokayo"  # ← укажи username своего канала
START_POINTS = 1000
BONUS_POINTS = 1000
BONUS_COOLDOWN_MINUTES = 60  # бонус раз в час

# Кэш username → user_id
usernames_cache = {}

# Загружаем или создаём файл с данными
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        users_data = json.load(f)
else:
    users_data = {}

# --- функции для работы с JSON ---
def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

def get_username_map():
    return users_data.setdefault("usernames", {})

def save_username(user, chat_id=None):
    """Сохраняем username (в нижнем регистре) и user_id в кэш и JSON.
       Также инициализируем очки, если нужно."""
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

# Загружаем кэш при старте
load_username_cache()

# --- функции для очков и бонусов ---
def get_user_points(chat_id, user_id):
    return users_data.get(str(chat_id), {}).get("points", {}).get(str(user_id), START_POINTS)

def update_user_points(chat_id, user_id, points):
    chat_data = users_data.setdefault(str(chat_id), {})
    points_data = chat_data.setdefault("points", {})
    points_data[str(user_id)] = get_user_points(chat_id, user_id) + points
    save_data()

def get_last_bonus_time(chat_id, user_id):
    return users_data.get(str(chat_id), {}).get("bonus_time", {}).get(str(user_id))

def set_last_bonus_time(chat_id, user_id):
    chat_data = users_data.setdefault(str(chat_id), {})
    bonus_data = chat_data.setdefault("bonus_time", {})
    bonus_data[str(user_id)] = datetime.now().isoformat()
    save_data()

# --- команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Команды бота:\n"
        "💰 !баланс — показать баланс\n"
        "🎰 !дэп <ставка> — сыграть в слот (например: !дэп 100)\n"
        "🎁 !бонус — получить бонус (раз в час)\n"
        "💸 !дать @логин 100 — перевести очки другому пользователю"
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

    message_text = update.message.text.strip().split()
    if len(message_text) > 1:
        try:
            bet = int(message_text[1])
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
                f"⏳ Ты уже получал бонус недавно. Попробуй снова через {minutes_left} мин {seconds_left} сек."
            )
            return

    update_user_points(chat_id, user.id, BONUS_POINTS)
    set_last_bonus_time(chat_id, user.id)
    await update.message.reply_text(
        f"🎁 Бонус успешно начислен! +{BONUS_POINTS} очков.\n"
        f"Текущий баланс: {get_user_points(chat_id, user.id)}"
    )

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)

    message_text = update.message.text.strip().split()
    if len(message_text) < 3:
        await update.message.reply_text("⚠️ Формат: !дать @логин количество")
        return

    username = message_text[1].lstrip("@").lower()
    try:
        amount = int(message_text[2])
    except ValueError:
        await update.message.reply_text("⚠️ Укажи корректное число очков для передачи")
        return

    if username not in usernames_cache:
        await update.message.reply_text("⚠️ Пользователь не найден")
        return

    target_id = usernames_cache[username]
    sender_points = get_user_points(chat_id, user.id)
    if amount > sender_points:
        await update.message.reply_text(f"⚠️ Недостаточно очков. Баланс: {sender_points}")
        return

    update_user_points(chat_id, user.id, -amount)
    update_user_points(chat_id, target_id, amount)
    await update.message.reply_text(f"💸 Ты передал {amount} очков @{username} ✅")

# --- универсальный обработчик для любых сообщений ---
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.from_user is None:
        return

    user = update.message.from_user
    chat_id = update.message.chat_id
    save_username(user, chat_id)  # сохраняем каждого пользователя

    text = update.message.text.lower()
    if text.startswith("!баланс"):
        await balance(update, context)
    elif text.startswith("!дэп"):
        await dep(update, context)
    elif text.startswith("!бонус"):
        await bonus(update, context)
    elif text.startswith("!дать"):
        await give(update, context)

# --- запуск ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    print("Бот запущен...")
    app.run_polling(drop_pending_updates=True)
