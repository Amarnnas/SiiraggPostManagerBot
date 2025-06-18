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

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
DATABASE_URL = os.getenv("DATABASE_URL")

class PostForm(StatesGroup):
    waiting_for_id = State()
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def insert_post(pool, post):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO posts(id, title, text, photo_file_id, message_id)
            VALUES($1, $2, $3, $4, $5)
        ''', post['id'], post['title'], post['text'], post.get('photo'), post['message_id'])

async def get_all_posts(pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title FROM posts ORDER BY id')

async def get_post_by_id(pool, post_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM posts WHERE id=$1', post_id)

async def delete_post(pool, post_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE id=$1', post_id)

async def id_exists(pool, post_id):
    async with pool.acquire() as conn:
        result = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE id=$1', post_id)
        return result > 0

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 عذرًا، هذا البوت مخصص لفريق سراج فقط.")
            return

        text = (
            "🌟 <b>مرحبًا بك في مخزن سراج</b> 🌟\n\n"
            "هذا البوت خُصِّص لحفظ منشورات الصفحة وتنظيمها بدقة،\n"
            "لتكون في متناول فريق سراج في أي وقت، وبسهولة ويسر.\n\n"
            "📌 يمكنك من خلال الخيارات التالية رفع منشور أو استعراض منشوراتك أو حذفها.\n\n"
            "💡 تذكَّر أن هذا العمل لوجه الله، وما كان لله دام واتّصل."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
            [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
            [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_id)
        await callback.message.answer("🔢 أرسل رقم معرف للمنشور (مثلاً: 101 أو t01)")
        await callback.answer()

    @dp.message(PostForm.waiting_for_id)
    async def receive_id(message: Message, state: FSMContext):
        post_id = message.text.strip()
        if await id_exists(pool, post_id):
            await message.answer("⚠️ هذا المعرف مستخدم من قبل، الرجاء اختيار رقم آخر.")
            return
        await state.update_data(id=post_id)
        await state.set_state(PostForm.waiting_for_title)
        await message.answer("📝 أرسل عنوان المنشور")

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("✏️ أرسل نص المنشور")

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ أرسل صورة (اختياري) أو أرسل /skip لتخطي")

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        data = await state.get_data()
        file_id = message.photo[-1].file_id
        await finalize_post_upload(bot, pool, message, state, data, file_id)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        data = await state.get_data()
        await finalize_post_upload(bot, pool, message, state, data, None)

    async def finalize_post_upload(bot, pool, message, state, data, photo):
        post_text = f"<b>{data['title']}</b>\n{data['text']}"
        if photo:
            sent = await bot.send_photo(CHANNEL_ID, photo=photo, caption=post_text, parse_mode=ParseMode.HTML)
        else:
            sent = await bot.send_message(CHANNEL_ID, text=post_text, parse_mode=ParseMode.HTML)

        await insert_post(pool, {
            "id": data['id'],
            "title": data['title'],
            "text": data['text'],
            "photo": photo,
            "message_id": sent.message_id
        })
        await message.answer("✅ تم رفع المنشور وتخزينه بنجاح.")
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.answer("📭 لا توجد منشورات حالياً.")
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("📌 اختر منشوراً من القائمة لعرضه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def view_selected(callback: CallbackQuery, state: FSMContext):
        post_id = callback.data.split("view_")[1]
        post = await get_post_by_id(pool, post_id)
        if not post:
            await callback.message.answer("❌ لم يتم العثور على منشور بهذا المعرف.")
        else:
            await bot.copy_message(chat_id=callback.message.chat.id, from_chat_id=CHANNEL_ID, message_id=post['message_id'])
        await callback.answer()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.answer("📭 لا توجد منشورات لحذفها.")
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("❌ اختر منشوراً لحذفه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("delete_"))
    async def delete_selected(callback: CallbackQuery, state: FSMContext):
        post_id = callback.data.split("delete_")[1]
        post = await get_post_by_id(pool, post_id)
        if not post:
            await callback.message.answer("❌ لم يتم العثور على منشور بهذا المعرف.")
        else:
            try:
                await bot.delete_message(chat_id=CHANNEL_ID, message_id=post['message_id'])
            except:
                pass
            await delete_post(pool, post_id)
            await callback.message.answer("🗑️ تم حذف المنشور بنجاح.")
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
