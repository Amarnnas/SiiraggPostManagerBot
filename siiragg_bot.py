import os
import asyncio
import asyncpg
from datetime import datetime
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
REVIEWERS = os.getenv("REVIEWERS", "").split(",")  # المراجعين والمشايخ
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
    waiting_for_review_note = State()


def main_menu_kb(is_reviewer=False):
    buttons = [
        [InlineKeyboardButton(text="➕ رفع منشور", callback_data="upload")],
        [InlineKeyboardButton(text="📚 عرض منشور", callback_data="view")],
        [InlineKeyboardButton(text="✏️ تعديل منشور", callback_data="edit")],
        [InlineKeyboardButton(text="🗑️ حذف منشور", callback_data="delete")],
    ]
    
    if is_reviewer:
        buttons.append([InlineKeyboardButton(text="🧾 المراجعة والتدقيق", callback_data="review_section")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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

def review_post_kb(post_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ يصلح للنشر", callback_data=f"approve_{post_id}")],
            [InlineKeyboardButton(text="❌ لا يصلح للنشر", callback_data=f"reject_{post_id}")],
            [InlineKeyboardButton(text="📝 يحتاج تعديل", callback_data=f"needs_edit_{post_id}")],
            [InlineKeyboardButton(text="🔄 تعديل التصنيف", callback_data=f"change_status_{post_id}")],
            [InlineKeyboardButton(text="🔙 رجوع للمراجعة", callback_data="review_section")]
        ]
    )

def confirm_review_kb(post_id, action):
    action_text = {
        'approve': 'اعتماد المنشور للنشر',
        'reject': 'رفض المنشور',
        'needs_edit': 'تحديد أن المنشور يحتاج تعديل'
    }
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تأكيد القرار", callback_data=f"confirm_{action}_{post_id}")],
            [InlineKeyboardButton(text="🔙 إلغاء", callback_data=f"review_post_{post_id}")]
        ]
    )

def change_status_kb(post_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏳ بانتظار المراجعة", callback_data=f"set_status_pending_{post_id}")],
            [InlineKeyboardButton(text="✅ معتمد للنشر", callback_data=f"set_status_approved_{post_id}")],
            [InlineKeyboardButton(text="❌ مرفوض", callback_data=f"set_status_rejected_{post_id}")],
            [InlineKeyboardButton(text="📝 يحتاج تعديل", callback_data=f"set_status_needs_edit_{post_id}")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data=f"review_post_{post_id}")]
        ]
    )

def view_categories_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ منشورات تمّت مراجعتها", callback_data="view_approved")],
            [InlineKeyboardButton(text="⏳ منشورات بانتظار المراجعة", callback_data="view_pending")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]
        ]
    )

async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def setup_database(pool):
    """إنشاء الجداول وإضافة الأعمدة الجديدة إن لم تكن موجودة"""
    async with pool.acquire() as conn:
        # إنشاء جدول المنشورات إن لم يكن موجوداً
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                photo_file_id TEXT,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # إضافة أعمدة المراجعة إن لم تكن موجودة
        try:
            await conn.execute('ALTER TABLE posts ADD COLUMN status TEXT DEFAULT \'pending\'')
        except:
            pass  # العمود موجود بالفعل
            
        try:
            await conn.execute('ALTER TABLE posts ADD COLUMN review_note TEXT')
        except:
            pass  # العمود موجود بالفعل
            
        try:
            await conn.execute('ALTER TABLE posts ADD COLUMN reviewed_by TEXT')
        except:
            pass  # العمود موجود بالفعل
            
        try:
            await conn.execute('ALTER TABLE posts ADD COLUMN reviewed_at TIMESTAMP')
        except:
            pass  # العمود موجود بالفعل

async def insert_post(pool, post):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO posts(title, text, photo_file_id, username, status)
            VALUES($1, $2, $3, $4, 'pending')
        ''', post['title'], post['text'], post.get('photo'), post['username'])

async def get_all_posts(pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title, status FROM posts ORDER BY id')

async def get_posts_by_status(pool, status):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title, status FROM posts WHERE status = $1 ORDER BY id', status)

async def get_posts_for_review(pool):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, title, status FROM posts ORDER BY id')

async def get_post_by_id(pool, post_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM posts WHERE id=$1', int(post_id))

async def delete_post(pool, post_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE id=$1', int(post_id))

async def update_post(pool, post_id, field, value):
    async with pool.acquire() as conn:
        await conn.execute(f'UPDATE posts SET {field}=$1 WHERE id=$2', value, post_id)

async def update_post_review_status(pool, post_id, status, reviewer_username, note=None):
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE posts 
            SET status=$1, reviewed_by=$2, reviewed_at=$3, review_note=$4 
            WHERE id=$5
        ''', status, reviewer_username, datetime.now(), note, post_id)

async def main():
    bot = Bot(token=TOKEN, session=AiohttpSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()
    
    # إعداد قاعدة البيانات
    await setup_database(pool)

    @dp.message(F.text.startswith("/start"))
    async def welcome(message: Message):
        if message.from_user.username not in ALLOWED_USERS:
            await message.answer("❌ البوت خاص بفريق سراج فقط، تواصل مع الإدارة للتفعيل.")
            return
        
        is_reviewer = message.from_user.username in REVIEWERS
        
        # Send spiritual reminder first
        await message.answer("🕊️ قبل أن تبدأ، تذكّر:\n\nاتقِ الله في عملك، وأخلص نيتك لله، ولا تكتب إلا ما صح عن النبي ﷺ، فإن الله مطلع على ما في قلبك ويعلم ما تقول.")
        
        # Then send the main welcome message with menu
        welcome_text = "السلام عليكم ورحمة الله وبركاته 🌿\n\nأهلاً وسهلاً بك في <b>مخزن سراج</b> هنا يمكنك إدارة منشوراتك:\n\n🔹 رفع منشور جديد\n🔹 عرض المنشورات\n🔹 تعديل المنشورات\n🔹 حذف المنشورات"
        
        if is_reviewer:
            welcome_text += "\n🔹 مراجعة وتدقيق المحتوى"
            
        welcome_text += "\n\nاختر ما يناسبك من القائمة أدناه 👇"
        
        await message.answer(welcome_text, reply_markup=main_menu_kb(is_reviewer))

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
        await message.answer("✅ تم رفع المنشور بنجاح وهو الآن بانتظار المراجعة والتدقيق من المشايخ الكرام. جزاك الله خير.", reply_markup=main_menu_kb(message.from_user.username in REVIEWERS))
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
        await message.answer("✅ تم رفع المنشور بدون صورة وهو الآن بانتظار المراجعة والتدقيق من المشايخ الكرام. بارك الله فيك.", reply_markup=main_menu_kb(message.from_user.username in REVIEWERS))
        await state.clear()

    @dp.callback_query(F.data == "view")
    async def handle_view(callback: CallbackQuery):
        await callback.message.edit_text("📚 اختر نوع المنشورات التي تريد عرضها:", reply_markup=view_categories_kb())

    @dp.callback_query(F.data == "view_approved")
    async def view_approved_posts(callback: CallbackQuery):
        posts = await get_posts_by_status(pool, 'approved')
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات مراجعة لعرضها.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=f"✅ {row['title']}", callback_data=f"show_post_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="view")]])
        await callback.message.edit_text("📚 المنشورات المراجعة والمعتمدة:", reply_markup=markup)

    @dp.callback_query(F.data == "view_pending")
    async def view_pending_posts(callback: CallbackQuery):
        posts = await get_posts_by_status(pool, 'pending')
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات بانتظار المراجعة.", reply_markup=back_to_main_kb())
            return
        buttons = [[InlineKeyboardButton(text=f"⏳ {row['title']}", callback_data=f"show_post_{row['id']}")] for row in posts]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="view")]])
        await callback.message.edit_text("📚 المنشورات بانتظار المراجعة:\n\n📌 لم يتم مراجعة هذه المنشورات بعد، فكن على يقظة قبل استخدامها", reply_markup=markup)

    @dp.callback_query(F.data.startswith("show_post_"))
    async def show_post(callback: CallbackQuery):
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"<b>{post['title']}</b>\n\n{post['text']}"
            
            # إضافة معلومات المراجعة
            if post['status'] == 'approved':
                msg += f"\n\n✅ <i>تمت مراجعة هذا المنشور وإقراره من قبل: {post['reviewed_by']}</i>"
            elif post['status'] == 'needs_edit' and post['review_note']:
                msg += f"\n\n📝 <i>ملاحظة المراجع المبارك:</i>\n{post['review_note']}"
            elif post['status'] == 'pending':
                msg += "\n\n⏳ <i>هذا المنشور بانتظار المراجعة</i>"
            
            if post['photo_file_id']:
                await callback.message.answer_photo(photo=post['photo_file_id'], caption=msg, reply_markup=back_to_main_kb())
            else:
                await callback.message.edit_text(msg, reply_markup=back_to_main_kb())
        else:
            await callback.message.edit_text("⛔️ المنشور غير موجود.", reply_markup=back_to_main_kb())

    # قسم المراجعة والتدقيق
    @dp.callback_query(F.data == "review_section")
    async def review_section(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ هذا القسم مخصص للمراجعين والمشايخ فقط", show_alert=True)
            return
            
        posts = await get_posts_for_review(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات للمراجعة.", reply_markup=back_to_main_kb())
            return
            
        buttons = []
        for row in posts:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'needs_edit': '📝'
            }.get(row['status'], '⏳')
            
            buttons.append([InlineKeyboardButton(
                text=f"{status_emoji} {row['title']}", 
                callback_data=f"review_post_{row['id']}"
            )])
            
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("🧾 اختر المنشور الذي تريد مراجعته وتدقيقه:\n\n⏳ بانتظار المراجعة\n✅ معتمد\n❌ مرفوض\n📝 يحتاج تعديل", reply_markup=markup)

    @dp.callback_query(F.data.startswith("review_post_"))
    async def review_post(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ هذا القسم مخصص للمراجعين والمشايخ فقط", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"🧾 <b>مراجعة المنشور:</b>\n\n<b>{post['title']}</b>\n\n{post['text']}"
            
            if post['status'] != 'pending':
                status_text = {
                    'approved': '✅ معتمد',
                    'rejected': '❌ مرفوض', 
                    'needs_edit': '📝 يحتاج تعديل'
                }.get(post['status'], '')
                msg += f"\n\n<i>الحالة الحالية: {status_text}</i>"
                if post['reviewed_by']:
                    msg += f"\n<i>راجعه: {post['reviewed_by']}</i>"
                if post['review_note']:
                    msg += f"\n<i>الملاحظة: {post['review_note']}</i>"
            
            if post['photo_file_id']:
                await callback.message.answer_photo(photo=post['photo_file_id'], caption=msg, reply_markup=review_post_kb(post_id))
            else:
                await callback.message.edit_text(msg, reply_markup=review_post_kb(post_id))
        else:
            await callback.message.edit_text("⛔️ المنشور غير موجود.", reply_markup=back_to_main_kb())

    # معالجة أزرار المراجعة مع التأكيد
    @dp.callback_query(F.data.startswith("approve_"))
    async def ask_approve_confirmation(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[1])
        post = await get_post_by_id(pool, post_id)
        if post:
            try:
    await callback.message.edit_text(
        f"📝 هل أنت متأكد من تحديد أن هذا المنشور يحتاج تعديل؟\n\n<b>{post['title']}</b>\n\nسيُطلب منك كتابة ملاحظة توجيهية للكاتب.",
        reply_markup=confirm_review_kb(post_id, 'needs_edit')
    )
except Exception:
    await callback.message.answer(
        f"📝 هل أنت متأكد من تحديد أن هذا المنشور يحتاج تعديل؟\n\n<b>{post['title']}</b>\n\nسيُطلب منك كتابة ملاحظة توجيهية للكاتب.",
        reply_markup=confirm_review_kb(post_id, 'needs_edit')
    )
    @dp.callback_query(F.data.startswith("reject_"))
    async def ask_reject_confirmation(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[1])
        post = await get_post_by_id(pool, post_id)
        if post:
            await callback.message.edit_text(
                f"❌ هل أنت متأكد من رفض هذا المنشور؟\n\n<b>{post['title']}</b>\n\nهذا القرار سيحجب المنشور عن أعضاء الفريق العاديين.",
                reply_markup=confirm_review_kb(post_id, 'reject')
            )

    @dp.callback_query(F.data.startswith("needs_edit_"))
    async def ask_needs_edit_confirmation(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            await callback.message.edit_text(
                f"📝 هل أنت متأكد من تحديد أن هذا المنشور يحتاج تعديل؟\n\n<b>{post['title']}</b>\n\nسيُطلب منك كتابة ملاحظة توجيهية للكاتب.",
                reply_markup=confirm_review_kb(post_id, 'needs_edit')
            )

    # تأكيد القرارات
    @dp.callback_query(F.data.startswith("confirm_approve_"))
    async def confirm_approve_post(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[2])
        await update_post_review_status(pool, post_id, 'approved', callback.from_user.username)
        await callback.message.edit_text("✅ تم اعتماد المنشور بنجاح. جزاك الله خيرًا على هذا التدقيق المبارك.", reply_markup=main_menu_kb(True))

    @dp.callback_query(F.data.startswith("confirm_reject_"))
    async def confirm_reject_post(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[2])
        await update_post_review_status(pool, post_id, 'rejected', callback.from_user.username)
        await callback.message.edit_text("❌ تم رفض المنشور. جزاك الله خيرًا على حرصك على سلامة المحتوى.", reply_markup=main_menu_kb(True))

    @dp.callback_query(F.data.startswith("confirm_needs_edit_"))
    async def confirm_needs_edit_post(callback: CallbackQuery, state: FSMContext):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[3])
        await state.update_data(review_post_id=post_id)
        await state.set_state(PostForm.waiting_for_review_note)
        await callback.message.edit_text("✒️ اكتب ملاحظتك المباركة على المنشور ليتم تعديله وفقًا لتوجيهك:")

    @dp.message(PostForm.waiting_for_review_note)
    async def receive_review_note(message: Message, state: FSMContext):
        data = await state.get_data()
        post_id = data['review_post_id']
        note = message.text
        
        await update_post_review_status(pool, post_id, 'needs_edit', message.from_user.username, note)
        await message.answer("📝 تم حفظ ملاحظتك المباركة. جزاك الله خيرًا على هذا التوجيه النافع.", reply_markup=main_menu_kb(True))
        await state.clear()

    # تعديل التصنيف
    @dp.callback_query(F.data.startswith("change_status_"))
    async def change_status_menu(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        post_id = int(callback.data.split("_")[2])
        post = await get_post_by_id(pool, post_id)
        if post:
            current_status = {
                'pending': '⏳ بانتظار المراجعة',
                'approved': '✅ معتمد للنشر',
                'rejected': '❌ مرفوض',
                'needs_edit': '📝 يحتاج تعديل'
            }.get(post['status'], 'غير محدد')
            
            await callback.message.edit_text(
                f"🔄 تعديل تصنيف المنشور:\n\n<b>{post['title']}</b>\n\nالتصنيف الحالي: {current_status}\n\nاختر التصنيف الجديد:",
                reply_markup=change_status_kb(post_id)
            )

    @dp.callback_query(F.data.startswith("set_status_"))
    async def set_new_status(callback: CallbackQuery):
        if callback.from_user.username not in REVIEWERS:
            await callback.answer("❌ غير مصرح لك بهذا الإجراء", show_alert=True)
            return
            
        parts = callback.data.split("_")
        new_status = parts[2]
        post_id = int(parts[3])
        
        await update_post_review_status(pool, post_id, new_status, callback.from_user.username)
        
        status_text = {
            'pending': '⏳ بانتظار المراجعة',
            'approved': '✅ معتمد للنشر',
            'rejected': '❌ مرفوض',
            'needs_edit': '📝 يحتاج تعديل'
        }.get(new_status, 'غير محدد')
        
        await callback.message.edit_text(
            f"✅ تم تعديل تصنيف المنشور بنجاح إلى: {status_text}\n\nبارك الله فيك على هذا التدقيق المبارك.",
            reply_markup=main_menu_kb(True)
        )

    @dp.callback_query(F.data == "edit")
    async def handle_edit(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات للتعديل.", reply_markup=back_to_main_kb())
            return
        buttons = []
        for row in posts:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'needs_edit': '📝'
            }.get(row['status'], '⏳')
            buttons.append([InlineKeyboardButton(text=f"{status_emoji} {row['title']}", callback_data=f"select_edit_{row['id']}")])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="🔙 رجوع", callback_data="back")]])
        await callback.message.edit_text("✏️ اختر المنشور الذي تريد تعديله:", reply_markup=markup)

    @dp.callback_query(F.data.startswith("select_edit_"))
    async def select_edit_post(callback: CallbackQuery, state: FSMContext):
        post_id = int(callback.data.split("_")[2])
        await state.update_data(edit_post_id=post_id)
        post = await get_post_by_id(pool, post_id)
        if post:
            msg = f"تعديل المنشور: <b>{post['title']}</b>\n\nاختر ما تريد تعديله:"
            if post['status'] == 'needs_edit' and post['review_note']:
                msg += f"\n\n📝 <i>ملاحظة المراجع:</i>\n{post['review_note']}"
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
        # إعادة تعيين حالة المنشور إلى pending بعد التعديل
        await update_post(pool, post_id, "status", "pending")
        await message.answer("✅ تم تغيير الصورة بنجاح وأُعيد المنشور لانتظار المراجعة. بارك الله فيك.", reply_markup=main_menu_kb(message.from_user.username in REVIEWERS))
        await state.clear()

    @dp.callback_query(F.data == "remove_photo")
    async def remove_photo(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        post_id = data['edit_post_id']
        
        await update_post(pool, post_id, "photo_file_id", None)
        # إعادة تعيين حالة المنشور إلى pending بعد التعديل
        await update_post(pool, post_id, "status", "pending")
        await callback.message.edit_text("✅ تم حذف الصورة بنجاح وأُعيد المنشور لانتظار المراجعة. بارك الله فيك.", reply_markup=main_menu_kb(callback.from_user.username in REVIEWERS))
        await state.clear()

    @dp.message(PostForm.waiting_for_edit_value)
    async def receive_edit_value(message: Message, state: FSMContext):
        data = await state.get_data()
        post_id = data['edit_post_id']
        field = data['edit_field']
        new_value = message.text
        
        await update_post(pool, post_id, field, new_value)
        # إعادة تعيين حالة المنشور إلى pending بعد التعديل
        await update_post(pool, post_id, "status", "pending")
        await message.answer("✅ تم تعديل المنشور بنجاح وأُعيد لانتظار المراجعة. بارك الله فيك.", reply_markup=main_menu_kb(message.from_user.username in REVIEWERS))
        await state.clear()

    @dp.callback_query(F.data == "delete")
    async def handle_delete(callback: CallbackQuery, state: FSMContext):
        posts = await get_all_posts(pool)
        if not posts:
            await callback.message.edit_text("❌ لا توجد منشورات لحذفها.", reply_markup=back_to_main_kb())
            return
        buttons = []
        for row in posts:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'needs_edit': '📝'
            }.get(row['status'], '⏳')
            buttons.append([InlineKeyboardButton(text=f"{status_emoji} {row['title']}", callback_data=f"ask_delete_{row['id']}")])
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
        await callback.message.edit_text("🗑️ تم حذف المنشور بنجاح. نسأل الله الإخلاص والقبول.", reply_markup=main_menu_kb(callback.from_user.username in REVIEWERS))

    @dp.callback_query(F.data == "back")
    async def go_back(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        is_reviewer = callback.from_user.username in REVIEWERS
        await callback.message.edit_text("🔙 رجعناك للقائمة الرئيسية جزاك الله خيرا 🌿", reply_markup=main_menu_kb(is_reviewer))

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
