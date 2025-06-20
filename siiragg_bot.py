# Telegram Bot for Managing Posts Without Channel (Database Only)

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
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
DATABASE_URL = os.getenv("DATABASE_URL")

class PostForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

class EditForm(StatesGroup):
    choosing_post = State()
    editing_field = State()
    editing_value = State()

# Keyboards
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
        [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
        [InlineKeyboardButton(text="📝 تعديل منشور", callback_data="edit")],
        [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")]
    ])

def back_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]]
    )

# Database helpers
async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def insert_post(pool, post):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO posts(title, text, photo_file_id, username)
            VALUES($1, $2, $3, $4)
        ''', post['title'], post['text'], post.get('photo'), post['username'])

async def get_all_posts(pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title FROM posts ORDER BY id')

async def get_post_by_id(pool, post_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM posts WHERE id=$1', int(post_id))

async def update_post(pool, post_id, field, value):
    async with pool.acquire() as conn:
        await conn.execute(f'UPDATE posts SET {field}=$1 WHERE id=$2', value, int(post_id))

async def delete_post(pool, post_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE id=$1', int(post_id))

# Bot
async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 البوت خاص بأعضاء الفريق فقط. تواصل مع الإدارة لإضافتك.")
            return

        await message.answer(
            "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
            "مرحبًا بك في <b>منصة إدارة المنشورات</b>.\n"
            "يمكنك رفع المنشورات، عرضها، تعديلها أو حذفها.\n\n"
            "بارك الله فيك وسدد خُطاك.",
            reply_markup=main_menu_kb()
        )

    @dp.callback_query(F.data == "upload")
    async def start_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 أرسل عنوان المنشور:", reply_markup=back_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def upload_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 قبل أن ترسل شئ إتقى الله فيما تكتب و إستحضر أن الله يرى ما تكتب و أخلص النيه لله ثم  أرسل نص المنشور :", reply_markup=back_kb())

    @dp.message(PostForm.waiting_for_text)
    async def upload_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ أرسل صورة (أو اكتب /skip للتجاوز):", reply_markup=back_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def upload_photo(message: Message, state: FSMContext):
        await state.update_data(photo=message.photo[-1].file_id)
        await finalize_upload(message, state, pool)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_photo(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_upload(message, state, pool)

    async def finalize_upload(message: Message, state: FSMContext, pool):
        data = await state.get_data()
        await insert_post(pool, {
            "title": data['title'],
            "text": data['text'],
            "photo": data.get('photo'),
            "username": message.from_user.username
        })
        await message.answer("✅ تم حفظ المنشور بنجاح، جزاك الله خيرًا.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def view_menu(callback: CallbackQuery):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات حالياً.", reply_markup=back_kb())
            return

        buttons = [[InlineKeyboardButton(text=post['title'], callback_data=f"view_{post['id']}")] for post in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر منشور لعرضه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def view_post(callback: CallbackQuery):
        post_id = callback.data.split("_")[1]
        post = await get_post_by_id(pool, post_id)
        if not post:
            await callback.message.edit_text("❌ لم يتم العثور على المنشور.", reply_markup=back_kb())
            return

        text = f"<b>{post['title']}</b>\n\n{post['text']}\n\n📎 @{post['username']}"
        if post['photo_file_id']:
            await callback.message.answer_photo(photo=post['photo_file_id'], caption=text, parse_mode=ParseMode.HTML)
        else:
            await callback.message.answer(text, parse_mode=ParseMode.HTML)
        await callback.answer()

    # back handler
    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery):
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية.", reply_markup=main_menu_kb())
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
