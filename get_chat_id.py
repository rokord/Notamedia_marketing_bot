import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(F.chat.type.in_({"group", "supergroup", "private"}))
async def echo_chat_id(message: Message):
    chat = message.chat
    await message.answer(f"chat.id = {chat.id}")
    print(f"Получено сообщение из чата {chat.title or chat.full_name} (id={chat.id})")

async def main():
    print("Бот запущен. Напишите что-нибудь в группе с ботом...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())