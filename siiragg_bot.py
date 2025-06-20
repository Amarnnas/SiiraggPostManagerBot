# كود متكامل لتعديل وحذف المنشورات من قاعدة البيانات فقط دون قناة

import os
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, InputMediaPhoto
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")

class PostForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

class EditPost(StatesGroup):
    choosing_post = State()
    editing_title = State()
    editing_text = State()
    editing_image = State()

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

async def delete_post(pool, post_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE id=$1', int(post_id))

async def update_post(pool, post_id, title=None, text=None, photo=None):
    async with pool.acquire() as conn:
        if title:
            await conn.execute('UPDATE posts SET title=$1 WHERE id=$2', title, post_id)
        if text:
            await conn.execute('UPDATE posts SET text=$1 WHERE id=$2', text, post_id)
        if photo:
            await conn.execute('UPDATE posts SET photo_file_id=$1 WHERE id=$2', photo, post_id)

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
            [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
            [InlineKeyboardButton(text="✏️ تعديل منشور", callback_data="edit")],
            [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")]
        ]
    )

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            return await message.answer("🚫 البوت فقط للمصرح لهم. اتصل بالإدارة.")

        await message.answer("""
السلام عليكم ورحمة الله وبركاته 🌿
حبااااابك في مخزن سراج 
هنا بتقدر:
➕ ترفع منشور جديد
📚 تعرض منشوراتك
✏️ تعديل أي منشور
🗑️ تحذف منشور بعد التأكيد
        """, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

    @dp.callback_query(F.data == "upload")
    async def start_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 قبل أن ترسل شئ إتقى الله فيما تكتب و إستحضر أن الله يرى ما تكتب و أخلص النيه لله ثم أرسل عنوان المنشور:", reply_markup=back_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def get_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 قبل أن ترسل شئ إتقى الله فيما تكتب و إستحضر أن الله يرى ما تكتب و أخلص النيه لله ثم  أرسل نص المنشور :", reply_markup=back_kb())

    @dp.message(PostForm.waiting_for_text)
    async def get_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ أرسل صورة أو اكتب /skip", reply_markup=back_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def get_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await finalize_upload(bot, pool, message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_upload(bot, pool, message, state)

    async def finalize_upload(bot, pool, message, state):
        data = await state.get_data()
        await insert_post(pool, {
            "title": data['title'],
            "text": data['text'],
            "photo": data.get("photo"),
            "username": message.from_user.username
        })
        await message.answer("✅ تم رفع المنشور، جزاك الله خير 🌸")
        await state.clear()

    @dp.callback_query(F.data == "edit")
    async def start_edit(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            return await callback.message.edit_text("❌ لا توجد منشورات.", reply_markup=back_kb())
        buttons = [[InlineKeyboardButton(text=post['title'], callback_data=f"edit_{post['id']}")] for post in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙", callback_data="back")]])
        await callback.message.edit_text("✏️ اختر منشور للتعديل:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("edit_"))
    async def choose_edit(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[1])
        await state.update_data(post_id=post_id)
        await state.set_state(EditPost.editing_title)
        await callback.message.edit_text("🖊️ أرسل العنوان الجديد أو /skip:", reply_markup=back_kb())

    @dp.message(EditPost.editing_title)
    async def edit_title(message: Message, state: FSMContext):
        if message.text != "/skip":
            data = await state.get_data()
            await update_post(pool, data['post_id'], title=message.text.strip())
        await state.set_state(EditPost.editing_text)
        await message.answer("🖊️ أرسل النص الجديد أو /skip:", reply_markup=back_kb())

    @dp.message(EditPost.editing_text)
    async def edit_text(message: Message, state: FSMContext):
        if message.text != "/skip":
            data = await state.get_data()
            await update_post(pool, data['post_id'], text=message.text.strip())
        await state.set_state(EditPost.editing_image)
        await message.answer("🖼️ أرسل صورة جديدة أو /skip:", reply_markup=back_kb())

    @dp.message(EditPost.editing_image, F.photo)
    async def edit_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        data = await state.get_data()
        await update_post(pool, data['post_id'], photo=file_id)
        await message.answer("✅ تم التعديل، جزاك الله خير على  حرصك على فعل الصواب")
        await state.clear()

    @dp.message(EditPost.editing_image, F.text == "/skip")
    async def skip_edit_image(message: Message, state: FSMContext):
        await message.answer("✅ تم التعديل بارك الله فيك.")
        await state.clear()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
