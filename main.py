import json
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

TOKEN = "8322042811:AAHzdQ-XFQvopNDSWXqe8zjeuvUjO0FH0ug"
DATA_FILE = Path("data.json")

# Загружаем или создаём файл с данными
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        users_data = json.load(f)
else:
    users_data = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

# Начальные очки
START_POINTS = 1000

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет!Сосал? Команды бота: !дэп и !баланс.")

def get_user_points(chat_id, user_id):
    """Возвращает очки пользователя в конкретном чате"""
    return users_data.get(str(chat_id), {}).get(str(user_id), START_POINTS)

def update_user_points(chat_id, user_id, points):
    """Обновляет очки пользователя в конкретном чате"""
    chat_data = users_data.setdefault(str(chat_id), {})
    chat_data[str(user_id)] = get_user_points(chat_id, user_id) + points
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

    # Снимаем 10 очков
    update_user_points(chat_id, user_id, -10)

    # Отправляем 🎰 (slot machine)
    sent = await update.message.reply_dice(emoji="🎰")
    
    await asyncio.sleep(2)  # ждём результат

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

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.from_user is None:
        return

    text = update.message.text.lower()
    if text == "!баланс":
        await balance(update, context)
    elif text == "!дэп":
        await dep(update, context)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    print("Бот запущен...")
    app.run_polling()
