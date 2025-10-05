import json
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

TOKEN = "8322042811:AAHzdQ-XFQvopNDSWXqe8zjeuvUjO0FH0ug"
DATA_FILE = Path("data.json")
CHANNEL_USERNAME = "@rewokayo"  # ← укажи username своего канала, например @mychannel
START_POINTS = 1000
BONUS_POINTS = 1000
BONUS_COOLDOWN_MINUTES = 60  # теперь бонус можно получать раз в 60 минут

# Загружаем или создаём файл с данными
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        users_data = json.load(f)
else:
    users_data = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Команды бота:\n"
        "💰 !баланс — показать баланс\n"
        "🎰 !дэп — сыграть в слот\n"
        "🎁 !бонус — получить бонус за подписку на канал (раз в час)"
    )

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

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    points = get_user_points(chat_id, user_id)
    await update.message.reply_text(f"У тебя {points} очков 🎯")

async def dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    points = get_user_points(chat_id, user_id)

    if points <= 0:
        await update.message.reply_text("У тебя нет очков 😢 Молись создателю, может выдаст)")
        return

    if points < 10:
        await update.message.reply_text("У тебя недостаточно очков для ставки 😔, додепа не будет...")
        return

    update_user_points(chat_id, user_id, -10)

    sent = await update.message.reply_dice(emoji="🎰")
    await asyncio.sleep(2)

    dice_value = sent.dice.value
    reward = 0
    if dice_value in [1, 22, 43]:
        reward = 100
    elif dice_value == 64:
        reward = 1000
    elif dice_value in [16, 32, 48]:
        reward = 10

    if reward > 0:
        update_user_points(chat_id, user_id, reward)
        await update.message.reply_text(
            f"🎉 С заносом {reward} очков! Текущий баланс: {get_user_points(chat_id, user_id)}"
        )
    else:
        await update.message.reply_text(
            f"Проебали😢! Текущий баланс: {get_user_points(chat_id, user_id)}"
        )

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
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

    # Проверка времени последнего бонуса
    last_bonus_time = get_last_bonus_time(chat_id, user_id)
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

    # Выдаём бонус
    update_user_points(chat_id, user_id, BONUS_POINTS)
    set_last_bonus_time(chat_id, user_id)
    await update.message.reply_text(
        f"🎁 Бонус успешно начислен! +{BONUS_POINTS} очков.\n"
        f"Текущий баланс: {get_user_points(chat_id, user_id)}"
    )

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.from_user is None:
        return

    text = update.message.text.lower()
    if text == "!баланс":
        await balance(update, context)
    elif text == "!дэп":
        await dep(update, context)
    elif text == "!бонус":
        await bonus(update, context)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    print("Бот запущен...")
    app.run_polling()
