# Telegram Bot for Managing Posts
# Updated with working view, delete from channel, and message_id tracking

from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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

TOKEN = "7517935433:AAH5o9RMy1UHaYl9k_VMrJgVyoKjTui9dfc"
CHANNEL_ID = "@siiragg_stoke"
ALLOWED_USERS = ["Ammarnasiiir"]
POSTS_FILE = "posts.json"

class PostForm(StatesGroup):
    waiting_for_id = State()
    waiting_for_title = State()
    waiting_for_text = State()
    waiting_for_image = State()

class EditForm(StatesGroup):
    waiting_for_edit_id = State()
    waiting_for_new_text = State()

class DeleteForm(StatesGroup):
    waiting_for_delete_id = State()

async def load_posts():
    if not os.path.exists(POSTS_FILE):
        return []
    with open(POSTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

async def save_posts(posts):
    with open(POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

async def id_exists(post_id):
    posts = await load_posts()
    return any(p['id'] == post_id for p in posts)

async def title_exists(title):
    posts = await load_posts()
    return any(p['title'] == title for p in posts)

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def start(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("🚫  لا تملك صلاحية استخدام هذا البوت تواصل مع تقني فريق سراج التقوى لتتمكن من الوصول للمميزات الخاصة بالبوت ")
            return
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ رفع منشور", callback_data="upload")
        kb.button(text="📚 عرض منشورات", callback_data="view")
        kb.button(text="⚙️ تعديل منشور", callback_data="edit")
        kb.button(text="🗑️ حذف منشور", callback_data="delete")
        await message.answer("🔘 الخيارات المتاحة:", reply_markup=kb.as_markup())

    @dp.callback_query(F.data == "upload")
    async def handle_upload(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PostForm.waiting_for_id)
        await callback.message.answer("🔢 أرسل رقم المنشور (ID):")
        await callback.answer()

    @dp.message(PostForm.waiting_for_id)
    async def receive_id(message: Message, state: FSMContext):
        post_id = message.text.strip()
        if await id_exists(post_id):
            await message.answer("⚠️ هذا الرقم مستخدم من قبل. اختر رقمًا مختلفًا.")
            return
        await state.update_data(id=post_id)
        await state.set_state(PostForm.waiting_for_title)
        await message.answer("📝 أرسل عنوان المنشور:")

    @dp.message(PostForm.waiting_for_title)
    async def receive_title(message: Message, state: FSMContext):
        title = message.text.strip()
        if await title_exists(title):
            await message.answer("⚠️ هذا العنوان مستخدم من قبل. اختر عنوانًا مختلفًا.")
            return
        await state.update_data(title=title)
        await state.set_state(PostForm.waiting_for_text)
        await message.answer("📄 أرسل نص المنشور:")

    @dp.message(PostForm.waiting_for_text)
    async def receive_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text)
        await state.set_state(PostForm.waiting_for_image)
        await message.answer("🖼️ أرسل صورة (اختياري). أرسل /skip لتخطي:")

    @dp.message(PostForm.waiting_for_image, F.photo)
    async def receive_image(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await show_review(message, state)

    @dp.message(PostForm.waiting_for_image, Command("skip"))
    async def skip_image(message: Message, state: FSMContext):
        await state.update_data(photo=None)
        await show_review(message, state)

    async def show_review(message: Message, state: FSMContext):
        data = await state.get_data()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ تأكيد الرفع", callback_data="confirm_upload")],
                [InlineKeyboardButton(text="❌ تجاهل التغييرات", callback_data="cancel_upload")]
            ]
        )
        await message.answer(
            f"📋 <b>مراجعة:</b>\n<b>ID:</b> {data['id']}\n<b>عنوان:</b> {data['title']}\n<b>النص:</b> {data['text']}\n<b>صورة:</b> {'نعم' if data['photo'] else 'لا'}",
            reply_markup=kb,
        )
        if data['photo']:
            await message.bot.send_photo(chat_id=message.chat.id, photo=data['photo'])

    @dp.callback_query(F.data == "confirm_upload")
    async def confirm_upload(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        text = f"<b>{data['title']}</b>\n\n{data['text']}"
        try:
            if data['photo']:
                sent = await callback.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=data['photo'],
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            else:
                sent = await callback.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            await callback.message.answer(f"❌ فشل في النشر:\n{e}")
            return

        posts = await load_posts()
        posts.append({
            "id": data['id'],
            "title": data['title'],
            "text": data['text'],
            "photo": data['photo'],
            "message_id": sent.message_id
        })
        await save_posts(posts)

        await callback.message.answer("✅ تم رفع المنشور بنجاح.")
        await state.clear()
        await callback.answer()

    @dp.callback_query(F.data == "cancel_upload")
    async def cancel_upload(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.answer("❌ تم تجاهل التغييرات.")
        await callback.answer()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery):
        posts = await load_posts()
        if not posts:
            await callback.message.answer("📭 لا توجد منشورات محفوظة.")
        else:
            await callback.message.answer("📚 <b>المنشورات المحفوظة:</b>", parse_mode=ParseMode.HTML)
            for post in posts:
                text = f"<b>{post['title']}</b>\n\n{post['text']}"
                if post['photo']:
                    await callback.bot.send_photo(chat_id=callback.message.chat.id, photo=post['photo'], caption=text)
                else:
                    await callback.bot.send_message(chat_id=callback.message.chat.id, text=text)
        await callback.answer()

    @dp.callback_query(F.data == "edit")
    async def handle_edit(callback: CallbackQuery, state: FSMContext):
        await state.set_state(EditForm.waiting_for_edit_id)
        await callback.message.answer("🆔 أرسل ID المنشور الذي تريد تعديله:")
        await callback.answer()

    @dp.message(EditForm.waiting_for_edit_id)
    async def receive_edit_id(message: Message, state: FSMContext):
        post_id = message.text.strip()
        posts = await load_posts()
        post = next((p for p in posts if p['id'] == post_id), None)
        if not post:
            await message.answer("❌ لا يوجد منشور بهذا الرقم.")
            return
        await state.update_data(edit_id=post_id)
        await state.set_state(EditForm.waiting_for_new_text)
        await message.answer("📝 أرسل النص الجديد:")

    @dp.message(EditForm.waiting_for_new_text)
    async def receive_new_text(message: Message, state: FSMContext):
        new_text = message.text.strip()
        data = await state.get_data()
        posts = await load_posts()
        for post in posts:
            if post['id'] == data['edit_id']:
                post['text'] = new_text
                break
        await save_posts(posts)
        await message.answer("✅ تم تعديل النص بنجاح.")
        await state.clear()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        await state.set_state(DeleteForm.waiting_for_delete_id)
        await callback.message.answer("🆔 أرسل ID المنشور الذي تريد حذفه:")
        await callback.answer()

    @dp.message(DeleteForm.waiting_for_delete_id)
    async def receive_delete_id(message: Message, state: FSMContext):
        post_id = message.text.strip()
        posts = await load_posts()
        post = next((p for p in posts if p['id'] == post_id), None)
        if not post:
            await message.answer("❌ لا يوجد منشور بهذا الرقم.")
        else:
            try:
                await message.bot.delete_message(chat_id=CHANNEL_ID, message_id=post["message_id"])
            except Exception as e:
                await message.answer(f"⚠️ لم أستطع حذف الرسالة من القناة:\n{e}")
            new_posts = [p for p in posts if p['id'] != post_id]
            await save_posts(new_posts)
            await message.answer("🗑️ تم حذف المنشور بنجاح.")
        await state.clear()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
