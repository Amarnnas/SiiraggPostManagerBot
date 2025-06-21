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

def confirm_delete_kb(post_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تأكيد الحذف", callback_data=f"confirm_delete_{post_id}")],
            [InlineKeyboardButton(text="🔙 إلغاء", callback_data="back")]
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

    @dp.callback_query(F.data == "upload")
    async def upload_post(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_title)
        await callback.message.edit_text("✍️ قبل أن تكتب عنوان منشورك، تذكّر أن الله يراك، وأن الكلمة أمانة.\n\nاختر عنوانًا يعبر عن الحق، ويهدي القلوب، ويكون شاهدًا لك لا عليك.\n\nأرسل الآن عنوان المنشور جزاك الله خيرًا:")

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text)
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📝 قبل أن تكتب محتوى منشورك، اجعل قلبك حاضرًا، ونيّتك صادقة.\n\nفإن الكلمة قد ترفعك عند الله، أو تهوي بك إن لم تتقِ فيها ربك.\n\nأرسل الآن نص المنشور، نفع الله بك:")

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text)
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ إن كانت الصورة تعين على الخير وتزيد المعنى وضوحًا، فأهلاً بها.\n\nاختر صورة طيبة، خالية من المنكرات، واعلم أن الله لا تخفى عليه نيتك.\n\nأرسل الصورة الآن، أو أرسل /skip لتخطيها:")

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        data = await state.get_data()
        photo_file_id = message.photo[-1].file_id
        post = {
            "title": data['title'],
            "text": data['text'],
            "photo": photo_file_id,
            "username": message.from_user.username
        }
        await insert_post(pool, post)
        await message.answer("✅ تم رفع المنشور بنجاح. جزاك الله خير.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.message(PostForm.waiting_for_image, F.text == "/skip")
    async def skip_image(message: Message, state: FSMContext):
        data = await state.get_data()
        post = {
            "title": data['title'],
            "text": data['text'],
            "photo": None,
            "username": message.from_user.username
        }
        await insert_post(pool, post)
        await message.answer("✅ تم رفع المنشور بدون صورة. بارك الله فيك.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات لعرضها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"show_post_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("📚 اختر المنشور الذي تريد عرضه:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("show_post_"))
    async def show_post(callback: CallbackQuery):
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"<b>{post['title']}</b>\n\n{post['text']}"
            if post['photo_file_id']:
                await callback.message.answer_photo(photo=post['photo_file_id'], caption=msg, reply_markup=back_to_main_kb())
            else:
                await callback.message.edit_text(msg, reply_markup=back_to_main_kb())
        else:
            await callback.message.edit_text("⛔️ المنشور غير موجود.", reply_markup=back_to_main_kb())

    @dp.callback_query(F.data == "edit")
    async def handle_edit(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات للتعديل.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"select_edit_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("✏️ اختر المنشور الذي تريد تعديله:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("select_edit_"))
    async def select_edit_post(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[2])
        await state.update_data(edit_post_id=post_id)
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"تعديل المنشور: <b>{post['title']}</b>\n\nاختر ما تريد تعديله:"
            await callback.message.edit_text(msg, reply_markup=edit_post_fields_kb())
        else:
            await callback.message.edit_text("⛔️ المنشور غير موجود.", reply_markup=back_to_main_kb())

    @dp.callback_query(F.data == "edit_title")
    async def edit_title(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_edit_value)
        await state.update_data(edit_field="title")
        await callback.message.edit_text("📝 أرسل العنوان الجديد:")

    @dp.callback_query(F.data == "edit_text")
    async def edit_text(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_edit_value)
        await state.update_data(edit_field="text")
        await callback.message.edit_text("📄 أرسل النص الجديد:")

    @dp.callback_query(F.data == "change_photo")
    async def change_photo(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_new_photo)
        await callback.message.edit_text("📤 أرسل الصورة الجديدة:")

    @dp.message(PostForm.waiting_for_new_photo, F.photo)
    async def receive_new_photo(message: Message, state: FSMContext):
        data = await state.get_data()
        post_id = data['edit_post_id']
        new_photo_file_id = message.photo[-1].file_id
        
        await update_post(pool, post_id, "photo_file_id", new_photo_file_id)
        await message.answer("✅ تم تغيير الصورة بنجاح. بارك الله فيك.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "remove_photo")
    async def remove_photo(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        post_id = data['edit_post_id']
        
        await update_post(pool, post_id, "photo_file_id", None)
        await callback.message.edit_text("✅ تم حذف الصورة بنجاح. بارك الله فيك.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.message(PostForm.waiting_for_edit_value)
    async def receive_edit_value(message: Message, state: FSMContext):
        data = await state.get_data()
        post_id = data['edit_post_id']
        field = data['edit_field']
        new_value = message.text
        
        await update_post(pool, post_id, field, new_value)
        await message.answer("✅ تم تعديل المنشور بنجاح. بارك الله فيك.", reply_markup=main_menu_kb())
        await state.clear()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات لحذفها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=row['title'], callback_data=f"ask_delete_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🗑️ اختر المنشور الذي تريد حذفه:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("ask_delete_"))
    async def ask_delete(callback: CallbackQuery):
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"⚠️ هل أنت متأكد أنك تريد حذف المنشور التالي؟\n\n<b>{post['title']}</b>"
            await callback.message.edit_text(msg, reply_markup=confirm_delete_kb(post_id))
        else:
            await callback.message.answer("⛔️ المنشور غير موجود.")

    @dp.callback_query(F.data.startswith("confirm_delete_"))
    async def confirm_delete(callback: CallbackQuery):
        post_id = int(callback.data.split("_")[2])
        await delete_post(pool, post_id)
        await callback.message.edit_text("🗑️ تم حذف المنشور بنجاح. نسأل الله الإخلاص والقبول.", reply_markup=main_menu_kb())

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية جزاك الله خيرا 🌿", reply_markup=main_menu_kb())

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())