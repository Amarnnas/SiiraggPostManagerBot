# Telegram Bot for Managing Posts with PostgreSQL Storage (Stable Version)

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
            await message.answer("🚫 هذا البوت مخصص فقط لفريق سراج. إذا كنت عضوًا في الفريق ولم يتم التعرف عليك، يرجى التواصل مع الإدارة.")
            return

        await message.answer("🔘 مرحباً بك في لوحة إدارة المنشورات. اختر ما تريد:", reply_markup=main_menu_kb())

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 أرسل عنوان المنشور (للتنظيم فقط، لا يظهر):", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 أرسل نص المنشور الآن.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ أرسل صورة (اختياري). أرسل /skip لتخطي.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await finalize_post_upload(bot, pool, message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_post_upload(bot, pool, message, state)

    async def finalize_post_upload(bot, pool, message, state):
        data = await state.get_data()
        photo = data.get("photo")
        caption = f"{data['text']}\n\n📎 نُشر بواسطة: @{message.from_user.username}"

        try:
            if photo:
                sent = await bot.send_photo(CHANNEL_ID, photo=photo, caption=caption, parse_mode=ParseMode.HTML)
            else:
                sent = await bot.send_message(CHANNEL_ID, text=caption, parse_mode=ParseMode.HTML)

            await insert_post(pool, {
                "title": data['title'],
                "text": data['text'],
                "photo": photo,
                "message_id": sent.message_id,
                "username": message.from_user.username
            })

            await message.answer("✅ تم رفع المنشور بنجاح.")
        except Exception as e:
            await message.answer(f"⚠️ حدث خطأ أثناء الرفع: {e}")

        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات حالياً.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر منشوراً لعرضه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def view_selected(callback: CallbackQuery, state: FSMContext):
        post_id = callback.data.split("view_")[1]
        post = await get_post_by_id(pool, post_id)
        if post:
            try:
                await bot.copy_message(chat_id=callback.message.chat.id, from_chat_id=CHANNEL_ID, message_id=post['message_id'])
            except:
                await callback.message.edit_text("⚠️ لا يمكن عرض المنشور (ربما تم حذفه من القناة).", reply_markup=back_to_main_kb())
        else:
            await callback.message.edit_text("❌ لم يتم العثور على المنشور المطلوب.", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات للحذف.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🗑️ اختر منشوراً لحذفه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("delete_"))
    async def delete_selected(callback: CallbackQuery, state: FSMContext):
        post_id = callback.data.split("delete_")[1]
        post = await get_post_by_id(pool, post_id)
        if post:
            try:
                await bot.delete_message(chat_id=CHANNEL_ID, message_id=post['message_id'])
            except:
                pass
            await delete_post(pool, post_id)
            await callback.message.edit_text("✅ تم حذف المنشور بنجاح.", reply_markup=back_to_main_kb())
        else:
            await callback.message.edit_text("❌ المنشور غير موجود.", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text("🔘 عدنا للقائمة الرئيسية.", reply_markup=main_menu_kb())
        await callback.answer()

    def main_menu_kb():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
                [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
                [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")]
            ]
        )

    def back_to_main_kb():
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]]
        )

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
