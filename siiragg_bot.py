# Telegram Bot for Managing Posts with PostgreSQL (No Channel Required)

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

TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
DATABASE_URL = os.getenv("DATABASE_URL")

class PostForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()
    waiting_for_edit_id = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()
    waiting_for_delete_confirm = State()
    waiting_for_new_photo = State()

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
            [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
            [InlineKeyboardButton(text="✏️ تعديل منشور", callback_data="edit")],
            [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")],
        ]
    )

def back_to_main_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]]
    )

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

async def update_post(pool, post_id, field, value):
    async with pool.acquire() as conn:
        await conn.execute(f'UPDATE posts SET {field}=$1 WHERE id=$2', value, post_id)

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 البوت خاص بفريق سراج فقط، تواصل مع الإدارة للتفعيل.")
            return
        await message.answer(
            "السلام عليكم ورحمة الله وبركاته 🌿\n\nأهلاً وسهلاً بك في <b>مخزن سراج</b>، هنا يمكنك إدارة منشوراتك بكل سهولة:\n\n"
            "➕ رفع منشور جديد\n📚 عرض المنشورات السابقة\n✏️ تعديل المنشورات\n🔟 حذف المنشورات\n\nاختر ما يناسبك من الخيارات أدناه 👇",
            reply_markup=main_menu_kb())

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 أرسل عنوان المنشور:", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 تمام، أرسل نص المنشور الآن.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ إذا عندك صورة أرسلها، أو أرسل /skip للتجاوز.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await finalize_upload(message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_upload(message, state)

    async def finalize_upload(message: Message, state: FSMContext):
        data = await state.get_data()
        await insert_post(pool, {
            "title": data['title'],
            "text": data['text'],
            "photo": data.get("photo"),
            "username": message.from_user.username
        })
        await message.answer("✅ تم حفظ المنشور في قاعدة البيانات، جزاك الله خير 🌸")
        await state.clear()

    @dp.callback_query(F.data == "edit")
    async def handle_edit(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات لتعديلها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"edit_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("✏️ اختر المنشور الذي ترغب بتعديله:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("edit_"))
    async def edit_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[1])
        await state.update_data(edit_id=post_id)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 العنوان", callback_data="field_title")],
            [InlineKeyboardButton(text="📝 النص", callback_data="field_text")],
            [InlineKeyboardButton(text="🖼️ الصورة - جديدة", callback_data="field_photo")],
            [InlineKeyboardButton(text="❌ حذف الصورة فقط", callback_data="field_remove_photo")]
        ])
        await callback.message.edit_text("اختر الجزء الذي تريد تعديله:", reply_markup=markup)

    @dp.callback_query(F.data == "field_photo")
    async def request_new_photo(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_new_photo)
        await callback.message.answer("🖼️ أرسل الصورة الجديدة الآن:")
        await callback.answer()

    @dp.message(PostForm.waiting_for_new_photo, F.photo)
    async def receive_new_photo(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        data = await state.get_data()
        await update_post(pool, data['edit_id'], "photo_file_id", file_id)
        await message.answer("✅ تم تحديث الصورة بنجاح.")
        await state.clear()

    @dp.callback_query(F.data == "field_remove_photo")
    async def remove_photo(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await update_post(pool, data['edit_id'], "photo_file_id", None)
        await callback.message.answer("✅ تم حذف الصورة من المنشور.")
        await state.clear()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery):
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية. جزاك الله خير 🌱", reply_markup=main_menu_kb())

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
