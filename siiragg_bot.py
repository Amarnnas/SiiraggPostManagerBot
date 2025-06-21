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

def edit_post_fields_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ تعديل العنوان", callback_data="edit_title")],
            [InlineKeyboardButton(text="📝 تعديل النص", callback_data="edit_text")],
            [InlineKeyboardButton(text="📤 تغيير الصورة", callback_data="change_photo")],
            [InlineKeyboardButton(text="🗑️ حذف الصورة فقط", callback_data="remove_photo")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]
        ]
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
            await message.answer("❌ البوت خاص بفريق سراج فقط، تواصل مع الإدارة للتفعيل.")
            return
        await message.answer(
            "السلام عليكم ورحمة الله وبركاته 🌿\n\nأهلاً وسهلاً بك في <b>مخزن سراج</b> هنا يمكنك إدارة منشوراتك:\n\n🔹 رفع منشور جديد\n🔹 عرض المنشورات\n🔹 تعديل المنشورات\n🔹 حذف المنشورات\n\nاختر ما يناسبك من القائمة أدناه 👇",
            reply_markup=main_menu_kb())

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📝 لا يوجد منشورات.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر المنشور:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("view_"))
    async def show_post(callback: CallbackQuery):
        post_id = int(callback.data.split("_")[1])
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"<b>{post['title']}</b>\n\n{post['text']}\n\n👤 @{post['username']}"
            if post['photo_file_id']:
                await callback.message.answer_photo(post['photo_file_id'], caption=msg, parse_mode=ParseMode.HTML)
            else:
                await callback.message.answer(msg, parse_mode=ParseMode.HTML)
        else:
            await callback.message.answer("⛔️ المنشور غير موجود.")

    @dp.callback_query(F.data == "edit")
    async def handle_edit(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات لتعديلها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"edit_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("✏️ اختر منشورًا لتعديله:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("edit_"))
    async def edit_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[1])
        await state.update_data(edit_id=post_id)
        await callback.message.edit_text("اختر الجزء الذي تريد تعديله:", reply_markup=edit_post_fields_kb())

    @dp.callback_query(F.data == "edit_title")
    async def edit_title(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.set_state(PostForm.waiting_for_edit_value)
        await state.update_data(field="title", edit_id=data['edit_id'])
        await callback.message.edit_text("✏️ أرسل العنوان الجديد الآن:")

    @dp.callback_query(F.data == "edit_text")
    async def edit_text(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.set_state(PostForm.waiting_for_edit_value)
        await state.update_data(field="text", edit_id=data['edit_id'])
        await callback.message.edit_text("📝 أرسل النص الجديد الآن:")

    @dp.callback_query(F.data == "change_photo")
    async def change_photo(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.set_state(PostForm.waiting_for_edit_value)
        await state.update_data(field="photo_file_id", edit_id=data['edit_id'])
        await callback.message.edit_text("📷 أرسل الصورة الجديدة الآن:")

    @dp.callback_query(F.data == "remove_photo")
    async def remove_photo(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await update_post(pool, data['edit_id'], "photo_file_id", None)
        await callback.message.edit_text("✅ تم حذف الصورة من المنشور.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.message(PostForm.waiting_for_edit_value)
    async def receive_new_value(message: Message, state: FSMContext):
        data = await state.get_data()

        if 'edit_id' not in data or 'field' not in data:
            await message.answer("⚠️ حصلت مشكلة في تحديد المنشور أو الحقل.")
            return

        field = data['field']

        if field == "photo_file_id":
            if not message.photo:
                await message.answer("❌ رجاءً أرسل صورة فقط.")
                return
            value = message.photo[-1].file_id
        else:
            value = message.text

        await update_post(pool, data['edit_id'], field, value)
        field_display = {
            "title": "العنوان",
            "text": "النص",
            "photo_file_id": "الصورة"
        }
        await message.answer(f"✅ تم تحديث {field_display.get(field, 'الحقل')} بنجاح.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery):
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية جزاك الله خيرا 🌿", reply_markup=main_menu_kb())

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
