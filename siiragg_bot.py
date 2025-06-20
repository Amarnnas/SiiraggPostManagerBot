# Telegram Bot for Managing Posts (No Channel Required)

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
        return await conn.fetch('SELECT id, title FROM posts ORDER BY id DESC')

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
            await message.answer("🚫 هذا البوت مخصص فقط للأعضاء المصرح لهم.")
            return

        text = (
            "السلام عليكم ورحمة الله وبركاته ✨\n\n"
            "<b>مرحبًا بك في بوت إدارة منشورات سراج!</b>\n\n"
            "🧰 من خلال هذا البوت يمكنك:\n"
            "➕ رفع منشور (نص + صورة اختيارية)\n"
            "📚 عرض المنشورات السابقة\n"
            "🗑️ حذف أي منشور\n\n"
            "💡 كل شيء يتم تخزينه في قاعدة البيانات ولا يتم النشر في أي قناة.\n"
            "ابدأ من القائمة أدناه 👇"
        )
        await message.answer(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 أرسل عنوان المنشور (للتنظيم فقط):", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 تمام، أرسل النص الآن.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ إذا عندك صورة أرسلها، أو اكتب /skip", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await finalize_post(bot, pool, message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_post(bot, pool, message, state)

    async def finalize_post(bot, pool, message, state):
        data = await state.get_data()
        try:
            await insert_post(pool, {
                "title": data['title'],
                "text": data['text'],
                "photo": data.get("photo"),
                "username": message.from_user.username
            })

            await message.answer("✅ تم حفظ المنشور في قاعدة البيانات.")
        except Exception as e:
            await message.answer(f"⚠️ حصل خطأ: {e}")
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات حاليًا.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر منشور لعرضه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def view_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("view_")[1])
        post = await get_post_by_id(pool, post_id)
        if post:
            text = f"{post['text']}\n\n📎 بواسطة: @{post['username']}"
            if post['photo_file_id']:
                await callback.message.answer_photo(post['photo_file_id'], caption=text)
            else:
                await callback.message.answer(text)
        else:
            await callback.message.answer("❌ لم يتم العثور على هذا المنشور.")
        await callback.answer()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات للحذف.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🗑️ اختر منشور لحذفه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("delete_"))
    async def delete_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("delete_")[1])
        await delete_post(pool, post_id)
        await callback.message.edit_text("✅ تم حذف المنشور.", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "🔙 رجعناك للقائمة الرئيسية.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
# Telegram Bot for Managing Posts (No Channel Required)

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
        return await conn.fetch('SELECT id, title FROM posts ORDER BY id DESC')

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
            await message.answer("🚫 هذا البوت مخصص فقط للأعضاء المصرح لهم.")
            return

        text = (
            "السلام عليكم ورحمة الله وبركاته ✨\n\n"
            "<b>مرحبًا بك في بوت إدارة منشورات سراج!</b>\n\n"
            "🧰 من خلال هذا البوت يمكنك:\n"
            "➕ رفع منشور (نص + صورة اختيارية)\n"
            "📚 عرض المنشورات السابقة\n"
            "🗑️ حذف أي منشور\n\n"
            "💡 كل شيء يتم تخزينه في قاعدة البيانات ولا يتم النشر في أي قناة.\n"
            "ابدأ من القائمة أدناه 👇"
        )
        await message.answer(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("📌 أرسل عنوان المنشور (للتنظيم فقط):", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 تمام، أرسل النص الآن.", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ إذا عندك صورة أرسلها، أو اكتب /skip", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await finalize_post(bot, pool, message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_post(bot, pool, message, state)

    async def finalize_post(bot, pool, message, state):
        data = await state.get_data()
        try:
            await insert_post(pool, {
                "title": data['title'],
                "text": data['text'],
                "photo": data.get("photo"),
                "username": message.from_user.username
            })

            await message.answer("✅ تم حفظ المنشور في قاعدة البيانات.")
        except Exception as e:
            await message.answer(f"⚠️ حصل خطأ: {e}")
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات حاليًا.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر منشور لعرضه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def view_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("view_")[1])
        post = await get_post_by_id(pool, post_id)
        if post:
            text = f"{post['text']}\n\n📎 بواسطة: @{post['username']}"
            if post['photo_file_id']:
                await callback.message.answer_photo(post['photo_file_id'], caption=text)
            else:
                await callback.message.answer(text)
        else:
            await callback.message.answer("❌ لم يتم العثور على هذا المنشور.")
        await callback.answer()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات للحذف.", reply_markup=back_to_main_kb())
            return

        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🗑️ اختر منشور لحذفه:", reply_markup=markup)
        await callback.answer()

    @dp.callback_query(F.data.startswith("delete_"))
    async def delete_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("delete_")[1])
        await delete_post(pool, post_id)
        await callback.message.edit_text("✅ تم حذف المنشور.", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "🔙 رجعناك للقائمة الرئيسية.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
