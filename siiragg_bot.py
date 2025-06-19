# Telegram Bot for Managing Posts with PostgreSQL Storage (Railway Compatible)

import os
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
DATABASE_URL = os.getenv("DATABASE_URL")

class PostForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def insert_post(pool, post):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO posts(title, text, photo_file_id, message_id, username)
            VALUES($1, $2, $3, $4, $5)
        ''', post['title'], post['text'], post.get('photo'), post['message_id'], post['username'])

async def get_all_posts(pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title FROM posts ORDER BY id')

async def get_post_by_id(pool, post_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM posts WHERE id=$1', int(post_id))

async def delete_post(pool, post_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE id=$1', int(post_id))

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 يا حبيب، البوت دا مُعدّ فقط لفريق سراج، ما بقدر تتابع هنا. أو للأسف إسمك غير مدرج في البوت إتواصل مع الفريق عشان تتحل المشكلة بإذن الله ")
            return

        text = (
            "السلام عليكم ورحمة الله وبركاته ✨\n\n"
            "يا رُفقة الدرب، يا من اختارهم الله لحمل هذا النور!\n"
            "أهلاً بيكم في <b>مخزن سراج</b>، المكان البيجمع منشوراتنا الدعوية بعناية.\n"
            "من هنا بننظم، بنوثّق، وبنرفع لله خالصًا.\n\n"
            "💡 خيّرك ظاهر قدامك، فابدأ بما يفتح الله لك."
        )
        await message.answer(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

    # ... باقي الكود كما هو دون تغيير

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
