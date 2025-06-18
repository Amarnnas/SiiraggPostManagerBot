# Telegram Bot for Managing Posts with Persistent Storage on Telegram Channel (via message_id)

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram import F
import asyncio
import json
import os

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ALLOWED_USERS = ["Ammarnasiiir"]
POSTS_FILE = "posts.json"

class PostForm(StatesGroup):
    waiting_for_id = State()
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

async def load_posts():
    if not os.path.exists(POSTS_FILE):
        return []
    with open(POSTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

async def save_posts(posts):
    with open(POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

async def get_post_by_id(post_id):
    posts = await load_posts()
    return next((p for p in posts if p['id'] == post_id), None)

async def id_exists(post_id):
    posts = await load_posts()
    return any(p['id'] == post_id for p in posts)

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫 عذرًا، هذا البوت مخصص لفريق سراج فقط.")
            return

        text = (
            "🌟 <b>مرحبًا بك في مخزن سراج</b> 🌟\n\n"
            "هذا البوت خُصِّص لحفظ منشورات الصفحة وتنظيمها بدقة،\n"
            "لتكون في متناول فريق سراج في أي وقت، وبسهولة ويسر.\n\n"
            "📌 يمكنك من خلال الخيارات التالية رفع منشور أو استعراض منشوراتك.\n\n"
            "💡 تذكَّر أن هذا العمل لوجه الله، وما كان لله دام واتّصل."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
            [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")]
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
        if await id_exists(post_id):
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
        await finalize_post_upload(bot, message, state, data, file_id)

    @dp.message(PostForm.waiting_for_image, Command("skip"))
    async def skip_image(message: Message, state: FSMContext):
        data = await state.get_data()
        await finalize_post_upload(bot, message, state, data, None)

    async def finalize_post_upload(bot: Bot, message: Message, state: FSMContext, data, photo):
        post_text = f"<b>{data['title']}</b>\n{data['text']}"
        if photo:
            sent = await bot.send_photo(CHANNEL_ID, photo=photo, caption=post_text, parse_mode=ParseMode.HTML)
        else:
            sent = await bot.send_message(CHANNEL_ID, text=post_text, parse_mode=ParseMode.HTML)

        posts = await load_posts()
        posts.append({"id": data['id'], "title": data['title'], "message_id": sent.message_id})
        await save_posts(posts)
        await message.answer("✅ تم رفع المنشور وتخزينه بنجاح.")
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery, state: FSMContext):
        await callback.message.answer("📌 أرسل رقم المعرف (ID) للمنشور الذي ترغب في عرضه:")
        await state.set_state(PostForm.waiting_for_id)
        await callback.answer()

    @dp.message(PostForm.waiting_for_id)
    async def view_by_id(message: Message, state: FSMContext):
        post_id = message.text.strip()
        post = await get_post_by_id(post_id)
        if not post:
            await message.answer("❌ لم يتم العثور على منشور بهذا المعرف.")
        else:
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=post['message_id'])
        await state.clear()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
