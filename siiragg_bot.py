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
            await message.answer("🚫 السلام عليكم ورحمة الله وبركاته يا أحباب 🌿 البوت دا خُصص لأهل سراج فقط، أهل الهمة والدعوة والتعاون على البر. لو ظهرت ليك الرسالة دي، فمعناها إنو حسابك لسه ما مُفعّل. نتمنى تتواصل مع الإدارة أو أحد أعضاء الفريق عشان يتم التفعيل. بارك الله فيك، ونفع الله بك. 💫.")
            return
        await message.answer("السلام عليكم ورحمة الله وبركاته 🌿\n\n حيّاك الله وبياك، ومرحبًا بك في <b>مخزن سراج</b> ✨\n المكان اللي بنرتّب فيه منشوراتنا الدعوية، بحُب وإخلاص.\n\n من خلال البوت دا، تقدر بكل يُسر:\n ➕ رفع منشور جديد\n 📚 عرض المنشورات السابقة\n✏️ تعديل المنشورات\n 🗑️ حذف المنشورات (مع تأكيد)\n\n" بارك الله فيك، واختر من الخيارات أدناه حسب الحاجة 🌱",
            reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML
        )

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

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"view_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر منشورًا لعرضه:", reply_markup=markup)

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
            await callback.message.answer("❌ لم يتم العثور على المنشور.")

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
            [InlineKeyboardButton(text="🖼️ الصورة", callback_data="field_photo")],
        ])
        await callback.message.edit_text("اختر الجزء الذي تريد تعديله:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("field_"))
    async def choose_field(callback: CallbackQuery, state: FSMContext):
        field = callback.data.split("_")[1]
        await state.update_data(field=field)
        await state.set_state(PostForm.waiting_for_edit_value)
        await callback.message.edit_text("✏️ أرسل القيمة الجديدة:")

    @dp.message(PostForm.waiting_for_edit_value)
    async def receive_edit_value(message: Message, state: FSMContext):
        data = await state.get_data()
        await update_post(pool, data['edit_id'], data['field'], message.text.strip())
        await message.answer("✅ تم تعديل المنشور بنجاح. بارك الله فيك 🌟")
        await state.clear()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("📭 لا توجد منشورات لحذفها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🗑️ اختر منشورًا لحذفه:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("delete_"))
    async def delete_selected(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[1])
        await state.update_data(delete_id=post_id)
        await state.set_state(PostForm.waiting_for_delete_confirm)
        await callback.message.answer("⚠️ تأكيد الحذف: أرسل كلمة (حذف) للتأكيد.")

    @dp.message(PostForm.waiting_for_delete_confirm)
    async def confirm_deletion(message: Message, state: FSMContext):
        if message.text.strip() == "حذف":
            data = await state.get_data()
            await delete_post(pool, data['delete_id'])
            await message.answer("✅ تم حذف المنشور بنجاح.")
        else:
            await message.answer("❌ لم يتم الحذف. تأكد من كتابة الكلمة بشكل صحيح.")
        await state.clear()

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery):
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية. جزاك الله خير 🌱", reply_markup=main_menu_kb())

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
