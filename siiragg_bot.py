# Telegram Bot for Managing Posts using Database Only (No Channel)

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
    confirming_delete = State()

async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
            [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
            [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")]
        ]
    )

def back_to_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])

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

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 المعذرة، هذا البوت خاص بفريق سراج. للتفعيل، تواصل مع الإدارة.")
            return

        await message.answer(
            "السلام عليكم ورحمة الله وبركاته 🌸\n\nمرحبا بك في <b>مخزن سراج</b>.\nيمكنك إدارة المنشورات الدعوية هنا مباشرة من دون الحاجة لقناة.\n\n🛠️ اختر من القائمة التالية ما تريد فعله:",
            reply_markup=main_menu_kb()
        )

    @dp.callback_query(F.data == "upload")
    async def start_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("✏️ أرسل عنوان المنشور:", reply_markup=back_to_main_kb())
        await callback.answer()

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip())
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 أرسل نص المنشور:", reply_markup=back_to_main_kb())

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text.strip())
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ إذا كان لديك صورة أرسلها الآن، أو اكتب /skip لتخطي.")

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_photo(message: Message, state: FSMContext):
        await state.update_data(photo=message.photo[-1].file_id)
        await finalize_upload(bot, pool, message, state)

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_photo(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await finalize_upload(bot, pool, message, state)

    async def finalize_upload(bot, pool, message, state):
        data = await state.get_data()
        await insert_post(pool, {
            "title": data["title"],
            "text": data["text"],
            "photo": data.get("photo"),
            "username": message.from_user.username
        })
        await message.answer("✅ تم حفظ المنشور في قاعدة البيانات، جزاك الله خيرًا!", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات حاليًا.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"view_{row['id']}")] for row in posts]
        buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="back")])
        await callback.message.edit_text("📚 اختر منشور لعرضه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()

    @dp.callback_query(F.data.startswith("view_"))
    async def show_post(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[1])
        post = await get_post_by_id(pool, post_id)
        if not post:
            await callback.message.edit_text("❌ المنشور غير موجود.", reply_markup=back_to_main_kb())
            return
        text = f"<b>{post['title']}</b>\n\n{post['text']}\n\n📎 بواسطة: @{post['username']}"
        if post['photo_file_id']:
            await bot.send_photo(callback.message.chat.id, photo=post['photo_file_id'], caption=text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(callback.message.chat.id, text, parse_mode=ParseMode.HTML)
        await callback.answer()

    @dp.callback_query(F.data == "delete")
    async def delete_list(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات للحذف.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row["title"], callback_data=f"delete_{row['id']}")] for row in posts]
        buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="back")])
        await callback.message.edit_text("🗑️ اختر منشورًا لحذفه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()

    @dp.callback_query(F.data.startswith("delete_"))
    async def confirm_delete(callback: CallbackQuery, state: FSMContext):
        post_id = callback.data.split("_")[1]
        await state.set_state(PostForm.confirming_delete)
        await state.update_data(post_id=post_id)
        await callback.message.edit_text("⚠️ هل أنت متأكد أنك تريد حذف هذا المنشور؟\nأرسل كلمة <code>حذف</code> للتأكيد.")
        await callback.answer()

    @dp.message(PostForm.confirming_delete)
    async def handle_delete_confirmation(message: Message, state: FSMContext):
        if message.text.strip() != "حذف":
            await message.answer("❌ تم إلغاء عملية الحذف.", reply_markup=main_menu_kb())
            await state.clear()
            return
        data = await state.get_data()
        await delete_post(pool, int(data["post_id"]))
        await message.answer("✅ تم حذف المنشور بنجاح، بارك الله فيك.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية، وفّقك الله في عملك الدعوي.", reply_markup=main_menu_kb())
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
