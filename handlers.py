import io
import json
import logging
import asyncio
import random
import string
from datetime import datetime

from pdf_export import generate_quiz_pdf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
import PyPDF2

from database import (
    get_user, create_user, update_user_attempts, update_user_points, get_point_transactions,
    add_referral, save_quiz, save_questions, get_quiz_questions,
    save_quiz_attempt, get_stats, get_all_users, ban_user, add_payment,
    set_user_attempts, get_user_by_username
)
from ai_quiz import (
    generate_quiz, detect_language, search_youtube,
    extract_topic_from_content, evaluate_qa_answer
)
from keyboards import (
    main_menu_keyboard, difficulty_keyboard, question_count_keyboard,
    question_type_keyboard, quiz_start_keyboard, mc_answer_keyboard,
    tf_answer_keyboard, payment_keyboard, admin_keyboard, back_keyboard
)

logger = logging.getLogger(__name__)
ADMIN_ID = 7021542402  # ضع معرف الأدمن الخاص بك هنا

MD = ParseMode.MARKDOWN


def esc(text: str) -> str:
    """تشفير النص لـ Markdown"""
    if not text:
        return ''
    s = str(text)
    for ch in ('\\', '_', '*', '`', '['):
        s = s.replace(ch, '\\' + ch)
    return s


def _gen_ref_code() -> str:
    """إنشاء كود إحالة عشوائي"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def get_or_create_user(user_id, username, first_name, last_name, referred_by=None):
    """الحصول على مستخدم أو إنشائه"""
    user = get_user(user_id)
    if not user:
        ref_code = _gen_ref_code()
        user = create_user(user_id, username or '', first_name or '',
                           last_name or '', ref_code, referred_by)
        if referred_by and user:
            add_referral(referred_by, user_id)
    return user


async def safe_edit(query, text, parse_mode=MD, reply_markup=None, **kwargs):
    """تعديل آمن مع تجنب الأخطاء"""
    try:
        await query.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs
        )
    except BadRequest as e:
        err = str(e).lower()
        if 'message is not modified' in err:
            return
        if 'parse' in err or 'entities' in err:
            plain = text.replace('*', '').replace('_', '').replace('`', '').replace('\\', '')
            try:
                await query.edit_message_text(plain, reply_markup=reply_markup)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"safe_edit error: {e}")


async def safe_reply(message, text, parse_mode=MD, reply_markup=None):
    """رد آمن مع تجنب الأخطاء"""
    try:
        await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if 'parse' in str(e).lower():
            plain = text.replace('*', '').replace('_', '').replace('`', '').replace('\\', '')
            try:
                await message.reply_text(plain, reply_markup=reply_markup)
            except Exception:
                pass


# ==================== أوامر البوت ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    try:
        user = update.effective_user
        args = context.args or []
        referred_by = None

        if args and args[0].startswith('ref_'):
            try:
                ref_id = int(args[0][4:])
                if ref_id != user.id:
                    referred_by = ref_id
            except (ValueError, IndexError):
                pass

        is_new_user = get_user(user.id) is None
        db_user = get_or_create_user(
            user.id, user.username, user.first_name, user.last_name, referred_by
        )
        
        if not db_user:
            await update.message.reply_text("❌ حدث خطأ في التسجيل. حاول مجدداً.")
            return

        if db_user.get('is_banned'):
            await update.message.reply_text("🚫 حسابك موقوف. تواصل مع الدعم: @zakros22bot")
            return

        lang = context.user_data.get('lang', 'ar')
        context.user_data['lang'] = lang
        context.user_data['user_id'] = user.id

        # إشعار الإحالة
        referral_notice = ""
        if is_new_user and referred_by:
            referrer = get_user(referred_by)
            if referrer:
                referrer_name = esc(referrer.get('first_name') or 'مستخدم')
                try:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=f"🎉 مبروك! حصلت على +0.2 نقطة من دعوة {esc(user.first_name or 'مستخدم')}!"
                    )
                except Exception:
                    pass
                referral_notice = f"\n\n✨ دخلت عبر رابط {referrer_name}!"

        points = float(db_user.get('points', 0))
        name = esc(user.first_name or 'مستخدم')

        if lang == 'ar':
            msg = (f"👋 مرحباً *{name}*!\n\n"
                   f"أنا *QuizBot* — مساعدك الذكي للدراسة 🎓\n\n"
                   f"أحوّل أي محاضرة أو نص أو PDF إلى اختبار تفاعلي!\n\n"
                   f"📊 نقاطك المتبقية: *{points:.1f}*\n"
                   f"🎁 ادعُ أصدقاء لتحصل على نقاط مجانية!"
                   f"{referral_notice}")
        else:
            msg = (f"👋 Welcome *{name}*!\n\n"
                   f"I'm *QuizBot* — Your AI Study Assistant 🎓\n\n"
                   f"I turn any lecture, text, or PDF into an interactive quiz!\n\n"
                   f"📊 Your remaining points: *{points:.1f}*\n"
                   f"🎁 Invite friends to earn free points!"
                   f"{referral_notice}")

        await update.message.reply_text(msg, parse_mode=MD, reply_markup=main_menu_keyboard(lang))

    except Exception as e:
        logger.error(f"cmd_start error: {e}", exc_info=True)
        await update.message.reply_text("❌ حدث خطأ. اكتب /start مجدداً.")


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القائمة الرئيسية"""
    lang = context.user_data.get('lang', 'ar')
    await update.message.reply_text("📋 القائمة الرئيسية:", reply_markup=main_menu_keyboard(lang))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم الأدمن"""
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🔧 *لوحة تحكم الإدارة*\n\nاختر إجراءً:",
        parse_mode=MD,
        reply_markup=admin_keyboard()
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل اللغة"""
    current = context.user_data.get('lang', 'ar')
    new_lang = 'en' if current == 'ar' else 'ar'
    context.user_data['lang'] = new_lang
    msg = "✅ تم التبديل إلى *العربية* 🇸🇦" if new_lang == 'ar' else "✅ Switched to *English* 🇬🇧"
    await update.message.reply_text(msg, parse_mode=MD, reply_markup=main_menu_keyboard(new_lang))


# ==================== معالجة النصوص والملفات ====================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النصوص المرسلة"""
    try:
        user = update.effective_user
        db_user = get_user(user.id)
        if not db_user:
            db_user = get_or_create_user(user.id, user.username, user.first_name, user.last_name)
        
        if not db_user or db_user.get('is_banned'):
            await safe_reply(update.message, "🚫 حسابك موقوف أو غير مسجل. اكتب /start")
            return

        context.user_data['user_id'] = user.id
        state = context.user_data.get('state')
        lang = context.user_data.get('lang', 'ar')
        text = update.message.text.strip()

        # معالجة الحالات الخاصة
        if state == 'waiting_admin_input':
            await handle_admin_text(update, context)
            return

        if state == 'answering_fill_blank':
            await process_text_answer(update, context, text, lang, is_fill_blank=True)
            return

        if state == 'waiting_qa_answer':
            await process_text_answer(update, context, text, lang, is_fill_blank=False)
            return

        # إنشاء اختبار جديد
        if len(text) < 20:
            msg = "⚠️ النص قصير جداً. أرسل محتوى أكثر (20 حرفاً على الأقل)." if lang == 'ar' else "⚠️ Text too short."
            await safe_reply(update.message, msg)
            return

        detected = detect_language(text)
        context.user_data['lang'] = detected
        context.user_data['content'] = text
        context.user_data['content_title'] = text[:60] + ('...' if len(text) > 60 else '')
        context.user_data['state'] = 'choosing_difficulty'

        msg = "🌍 اللغة المكتشفة: *العربية* ✅\n\nاختر مستوى الصعوبة:" if detected == 'ar' else "🌍 Language detected: *English* ✅\n\nChoose difficulty level:"
        await safe_reply(update.message, msg, parse_mode=MD, reply_markup=difficulty_keyboard(detected))

    except Exception as e:
        logger.error(f"handle_text_input error: {e}", exc_info=True)
        await update.message.reply_text("❌ حدث خطأ. اكتب /start للبدء من جديد.")


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ملفات PDF"""
    processing_msg = None
    try:
        user = update.effective_user
        db_user = get_user(user.id)
        if not db_user:
            db_user = get_or_create_user(user.id, user.username, user.first_name, user.last_name)
        
        if not db_user or db_user.get('is_banned'):
            await safe_reply(update.message, "🚫 حسابك موقوف.")
            return

        lang = context.user_data.get('lang', 'ar')
        doc = update.message.document
        
        if not doc:
            await safe_reply(update.message, "❌ لا يوجد ملف.")
            return

        mime = (doc.mime_type or '').lower()
        fname = (doc.file_name or '').lower()
        
        if 'pdf' not in mime and not fname.endswith('.pdf'):
            await safe_reply(update.message, "❌ هذا الملف ليس PDF. أرسل ملف PDF فقط.")
            return

        if doc.file_size and doc.file_size > 20 * 1024 * 1024:
            await safe_reply(update.message, "❌ الملف كبير جداً. الحد الأقصى 20 ميجابايت.")
            return

        processing_msg = await update.message.reply_text("⏳ جاري تنزيل الملف..." if lang == 'ar' else "⏳ Downloading file...")

        try:
            file = await asyncio.wait_for(doc.get_file(), timeout=30)
            file_bytes = await asyncio.wait_for(file.download_as_bytearray(), timeout=60)
        except asyncio.TimeoutError:
            await processing_msg.edit_text("❌ انتهت مهلة التنزيل. حاول مجدداً.")
            return

        await processing_msg.edit_text("⏳ جاري قراءة الملف..." if lang == 'ar' else "⏳ Reading file...")

        text = ''
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                await processing_msg.edit_text("❌ الملف محمي بكلمة مرور.")
                return
            for pg in reader.pages:
                try:
                    pg_text = pg.extract_text()
                    if pg_text:
                        text += pg_text + '\n'
                    if len(text) > 10000:
                        break
                except Exception:
                    continue
        except Exception as pdf_err:
            logger.error(f"PDF parse error: {pdf_err}")
            await processing_msg.edit_text("❌ تعذّر قراءة هذا الملف.")
            return

        text = text.strip()
        if len(text) < 30:
            await processing_msg.edit_text("❌ لا يمكن استخراج نص من هذا الملف.")
            return

        detected = detect_language(text)
        context.user_data['lang'] = detected
        context.user_data['content'] = text[:8000]
        context.user_data['content_title'] = doc.file_name or 'PDF Document'
        context.user_data['state'] = 'choosing_difficulty'

        chars = len(text)
        msg = (f"✅ تم استخراج *{chars:,}* حرف من الملف!\n\n🌍 اللغة المكتشفة: *العربية*\n\nاختر مستوى الصعوبة:" if detected == 'ar' 
               else f"✅ Extracted *{chars:,}* characters!\n\n🌍 Language: *English*\n\nChoose difficulty:")
        
        await processing_msg.edit_text(msg, parse_mode=MD, reply_markup=difficulty_keyboard(detected))

    except Exception as e:
        logger.error(f"handle_pdf error: {e}", exc_info=True)
        if processing_msg:
            try:
                await processing_msg.edit_text("❌ حدث خطأ أثناء معالجة الملف.")
            except Exception:
                pass


# ==================== معالجة الأزرار ====================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع أزرار البوت"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    try:
        data = query.data
        user = update.effective_user
        db_user = get_user(user.id)
        
        if not db_user:
            db_user = get_or_create_user(user.id, user.username, user.first_name, user.last_name)
        
        if not db_user or db_user.get('is_banned'):
            await safe_edit(query, "🚫 حسابك موقوف.", parse_mode=None)
            return

        context.user_data['user_id'] = user.id
        lang = context.user_data.get('lang', 'ar')

        # قائمة الأزرار
        if data == 'back_main':
            await show_main_menu(query, context, db_user, lang)
        elif data == 'new_quiz':
            await start_new_quiz(query, context, lang)
        elif data == 'my_stats':
            await show_stats(query, db_user, lang)
        elif data == 'referral':
            await show_referral(query, context, db_user, lang)
        elif data == 'buy_attempts':
            await show_buy_attempts(query, lang)
        elif data == 'help':
            await show_help(query, lang)
        elif data == 'pay_stars':
            await show_pay_stars(query, lang)
        elif data == 'toggle_lang':
            await toggle_language(query, context, db_user, lang)
        elif data.startswith('diff_'):
            await handle_difficulty(query, context, lang, data)
        elif data.startswith('qcount_'):
            await handle_question_count(query, context, db_user, lang, data)
        elif data.startswith('qtype_'):
            await handle_question_type_toggle(query, context, lang, data)
        elif data == 'do_generate':
            await generate_quiz_with_progress(query, context, lang)
        elif data.startswith('start_quiz_'):
            quiz_id = int(data.split('_')[2])
            await start_quiz(query, context, db_user, lang, quiz_id)
        elif data.startswith('export_quiz_'):
            quiz_id = int(data.split('_')[2])
            await export_quiz_pdf(query, context, quiz_id, lang)
        elif data.startswith('ans_'):
            await handle_answer(query, context, lang, data)
        elif data.startswith('admin_'):
            if user.id != ADMIN_ID:
                await safe_edit(query, "❌ ليس لديك صلاحية.", parse_mode=None)
                return
            await handle_admin_actions(query, context, data)
        else:
            logger.warning(f"Unknown callback: {data}")

    except Exception as e:
        logger.error(f"handle_callback error: {e}", exc_info=True)
        try:
            await safe_edit(query, "❌ حدث خطأ. حاول مجدداً.", parse_mode=None)
        except Exception:
            pass


async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الانتقال إلى السؤال التالي"""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    
    try:
        idx = int(query.data.split('_')[2])
        questions = context.user_data.get('questions', [])
        lang = context.user_data.get('lang', 'ar')
        
        if not questions:
            await safe_edit(query, "❌ لا توجد أسئلة.", parse_mode=None)
            return
        
        await send_question(query, context, questions, idx, lang)
    except Exception as e:
        logger.error(f"handle_next_question error: {e}")
        await safe_edit(query, "❌ خطأ. حاول مجدداً.", parse_mode=None)


# ==================== دوال مساعدة للأزرار ====================

async def show_main_menu(query, context, db_user, lang):
    """عرض القائمة الرئيسية"""
    attempts = db_user.get('attempts', 0)
    txt = (f"📋 *القائمة الرئيسية*\n\n📊 محاولاتك: *{attempts}*" if lang == 'ar'
           else f"📋 *Main Menu*\n\n📊 Your attempts: *{attempts}*")
    await safe_edit(query, txt, reply_markup=main_menu_keyboard(lang))


async def start_new_quiz(query, context, lang):
    """بدء إنشاء اختبار جديد"""
    msg = ("📚 *إنشاء اختبار جديد*\n\nأرسل المحتوى الذي تريد اختباراً منه:\n\n📄 *نص:* الصق النص مباشرة\n📑 *PDF:* أرسل ملف PDF"
           if lang == 'ar' else "📚 *Create New Quiz*\n\nSend the content:\n\n📄 *Text:* Paste text\n📑 *PDF:* Send PDF file")
    await safe_edit(query, msg, reply_markup=back_keyboard(lang))
    context.user_data['state'] = 'waiting_content'


async def show_stats(query, db_user, lang):
    """عرض إحصائيات المستخدم"""
    name = esc(db_user.get('first_name') or ('غير محدد' if lang == 'ar' else 'N/A'))
    pts = float(db_user.get('points', 0))
    
    if lang == 'ar':
        msg = (f"📊 *إحصائياتك*\n\n👤 الاسم: {name}\n💰 *رصيد النقاط: {pts:.1f}*\n📝 الاختبارات المكتملة: *{db_user.get('total_quizzes', 0)}*\n👥 الأصدقاء المدعوون: *{db_user.get('invited_count', 0)}*")
    else:
        msg = (f"📊 *Your Statistics*\n\n👤 Name: {name}\n💰 *Points: {pts:.1f}*\n📝 Quizzes: *{db_user.get('total_quizzes', 0)}*\n👥 Invited: *{db_user.get('invited_count', 0)}*")
    
    await safe_edit(query, msg, reply_markup=back_keyboard(lang))


async def show_referral(query, context, db_user, lang):
    """عرض نظام الإحالة"""
    bot_username = context.bot.username or 'QuizBot'
    ref_link = f"https://t.me/{bot_username}?start=ref_{db_user['user_id']}"
    pts = float(db_user.get('points', 0))
    
    if lang == 'ar':
        msg = (f"🎁 *نظام الإحالة*\n\nرابط دعوتك:\n`{ref_link}`\n\n📊 *كيف يعمل:*\n• كل دعوة = +0.2 نقطة\n• كل 5 دعوات = +1 محاولة مجانية\n\n👥 المدعوون: *{db_user.get('invited_count', 0)}*\n⭐ نقاطك: *{pts:.1f}*")
    else:
        msg = (f"🎁 *Referral System*\n\nYour link:\n`{ref_link}`\n\n📊 *How it works:*\n• Each invite = +0.2 points\n• Every 5 invites = +1 attempt\n\n👥 Invited: *{db_user.get('invited_count', 0)}*\n⭐ Points: *{pts:.1f}*")
    
    await safe_edit(query, msg, reply_markup=back_keyboard(lang))


async def show_buy_attempts(query, lang):
    """عرض خيارات شراء المحاولات"""
    if lang == 'ar':
        msg = ("💳 *شراء المحاولات*\n\n🎫 *السعر:* 10 محاولات = 5 ماستر (4 دولار)\n\n*طرق الدفع:*\n⭐ *نجوم تيليجرام* — ادفع مباشرة\n💳 *ماستركارد* — تواصل مع المالك\n\n📞 تواصل: @zakros22bot")
    else:
        msg = ("💳 *Buy Attempts*\n\n🎫 *Price:* 10 attempts = 5 Masters ($4)\n\n*Payment Methods:*\n⭐ *Telegram Stars* — Pay directly\n💳 *MasterCard* — Contact owner\n\n📞 Contact: @zakros22bot")
    
    await safe_edit(query, msg, parse_mode="MarkdownV2", reply_markup=payment_keyboard(lang))


async def show_help(query, lang):
    """عرض المساعدة"""
    if lang == 'ar':
        msg = ("ℹ️ *كيفية الاستخدام*\n\n1. اضغط 'إنشاء اختبار جديد'\n2. أرسل نصاً أو ملف PDF\n3. اختر الصعوبة وعدد الأسئلة\n4. ابدأ الاختبار\n\n⏱ كل سؤال: دقيقة واحدة\n📊 ترى نتيجتك عند الانتهاء")
    else:
        msg = ("ℹ️ *How to Use*\n\n1. Tap 'Create New Quiz'\n2. Send text or PDF\n3. Choose difficulty and count\n4. Start the quiz\n\n⏱ Each question: 1 minute\n📊 See your score when done")
    
    await safe_edit(query, msg, reply_markup=back_keyboard(lang))


async def show_pay_stars(query, lang):
    """عرض دفع النجوم"""
    if lang == 'ar':
        msg = ("⭐ *الدفع بنجوم تيليجرام*\n\n10 محاولات = 5 ماستر (4 دولار)\n\nتواصل مع المالك لإتمام الدفع.")
    else:
        msg = ("⭐ *Pay with Telegram Stars*\n\n10 attempts = 5 Masters ($4)\n\nContact the owner to complete payment.")
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 @zakros22bot", url="https://t.me/zakros22bot")],
        [InlineKeyboardButton("🏠 الرئيسية" if lang == 'ar' else "🏠 Main Menu", callback_data="back_main")],
    ])
    await safe_edit(query, msg, parse_mode="MarkdownV2", reply_markup=kb)


async def toggle_language(query, context, db_user, lang):
    """تبديل اللغة"""
    new_lang = 'en' if lang == 'ar' else 'ar'
    context.user_data['lang'] = new_lang
    attempts = db_user.get('attempts', 0)
    
    if new_lang == 'ar':
        msg = f"✅ تم التبديل إلى *العربية* 🇸🇦\n\n📊 محاولاتك: *{attempts}*"
    else:
        msg = f"✅ Switched to *English* 🇬🇧\n\n📊 Your attempts: *{attempts}*"
    
    await safe_edit(query, msg, reply_markup=main_menu_keyboard(new_lang))


async def handle_difficulty(query, context, lang, data):
    """معالجة اختيار الصعوبة"""
    difficulty = data.split('_')[1]
    if difficulty not in ('easy', 'medium', 'hard'):
        await safe_edit(query, "❌ خيار غير صالح.", parse_mode=None)
        return

    content = context.user_data.get('content', '')
    if not content or len(content.strip()) < 20:
        msg = "❌ لم يتم العثور على محتوى. أرسل نصاً أو PDF أولاً." if lang == 'ar' else "❌ No content found."
        await safe_edit(query, msg, parse_mode=None, reply_markup=back_keyboard(lang))
        context.user_data['state'] = 'waiting_content'
        return

    context.user_data['difficulty'] = difficulty
    context.user_data['state'] = 'choosing_count'
    msg = "🔢 *كم عدد الأسئلة التي تريدها؟*" if lang == 'ar' else "🔢 *How many questions?*"
    await safe_edit(query, msg, reply_markup=question_count_keyboard(lang))


async def handle_question_count(query, context, db_user, lang, data):
    """معالجة اختيار عدد الأسئلة"""
    content = context.user_data.get('content', '')
    difficulty = context.user_data.get('difficulty', 'medium')

    if not content or len(content.strip()) < 20:
        msg = "❌ المحتوى غير موجود. ابدأ من جديد." if lang == 'ar' else "❌ Content not found."
        await safe_edit(query, msg, parse_mode=None, reply_markup=back_keyboard(lang))
        context.user_data['state'] = 'waiting_content'
        return

    count_str = data.split('_')[1]
    if count_str == 'auto':
        words = len(content.split())
        if words < 100:
            count = 5
        elif words < 300:
            count = 10
        elif words < 700:
            count = 20
        elif words < 1500:
            count = 30
        else:
            count = 50
    else:
        try:
            count = int(count_str)
        except ValueError:
            count = 10

    count = max(5, min(100, count))
    context.user_data['question_count'] = count
    context.user_data['db_user_id'] = db_user['user_id']

    if 'selected_types' not in context.user_data:
        context.user_data['selected_types'] = ['multiple_choice', 'true_false', 'fill_blank', 'qa']

    selected = context.user_data['selected_types']

    if lang == 'ar':
        msg = f"🎛 *اختر أنواع الأسئلة*\n\nاضغط على نوع لتفعيله ✅ أو إلغائه ⬜\nثم اضغط *توليد الأسئلة الآن*\n\n📊 عدد الأسئلة: *{count}*"
    else:
        msg = f"🎛 *Choose Question Types*\n\nTap to enable ✅ or disable ⬜\nThen tap *Generate Questions Now*\n\n📊 Questions: *{count}*"

    await safe_edit(query, msg, reply_markup=question_type_keyboard(lang, selected))


async def handle_question_type_toggle(query, context, lang, data):
    """تبديل نوع السؤال"""
    type_map = {
        'qtype_mc': 'multiple_choice',
        'qtype_tf': 'true_false',
        'qtype_fb': 'fill_blank',
        'qtype_qa': 'qa',
    }
    toggle_type = type_map.get(data)
    if not toggle_type:
        return

    selected = context.user_data.get('selected_types', ['multiple_choice', 'true_false', 'fill_blank', 'qa'])

    if toggle_type in selected:
        if len(selected) > 1:
            selected = [t for t in selected if t != toggle_type]
    else:
        selected = selected + [toggle_type]

    context.user_data['selected_types'] = selected
    count = context.user_data.get('question_count', 10)

    if lang == 'ar':
        msg = f"🎛 *اختر أنواع الأسئلة*\n\nاضغط على نوع لتفعيله ✅ أو إلغائه ⬜\nثم اضغط *توليد الأسئلة الآن*\n\n📊 عدد الأسئلة: *{count}*"
    else:
        msg = f"🎛 *Choose Question Types*\n\nTap to enable ✅ or disable ⬜\nThen tap *Generate Questions Now*\n\n📊 Questions: *{count}*"

    await safe_edit(query, msg, reply_markup=question_type_keyboard(lang, selected))


def make_progress_bar(pct: int) -> str:
    """إنشاء شريط تقدم بصري"""
    filled = round(pct / 10)
    return '█' * filled + '▱' * (10 - filled)


async def generate_quiz_with_progress(query, context, lang):
    """توليد الأسئلة مع شريط تقدم"""
    content = context.user_data.get('content', '')
    difficulty = context.user_data.get('difficulty', 'medium')
    count = context.user_data.get('question_count', 10)
    selected_types = context.user_data.get('selected_types', ['multiple_choice', 'true_false', 'fill_blank', 'qa'])
    user_id = context.user_data.get('db_user_id') or context.user_data.get('user_id')

    if not content or len(content.strip()) < 20:
        msg = "❌ المحتوى غير موجود. ابدأ من جديد." if lang == 'ar' else "❌ Content not found."
        await safe_edit(query, msg, parse_mode=None, reply_markup=back_keyboard(lang))
        return

    # عرض بداية التوليد
    bar = make_progress_bar(0)
    init_msg = f"⚙️ *جاري توليد {count} سؤال...*\n\n`{bar}` *0%*\n\n🤖 الذكاء الاصطناعي يعمل..." if lang == 'ar' else f"⚙️ *Generating {count} questions...*\n\n`{bar}` *0%*\n\n🤖 AI is working..."
    await safe_edit(query, init_msg)

    # توليد الأسئلة
    loop = asyncio.get_event_loop()
    
    try:
        questions = await loop.run_in_executor(
            None, generate_quiz, content, count, difficulty, lang, selected_types
        )
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        msg = f"❌ *فشل توليد الأسئلة*\n\n{esc(str(e))}" if lang == 'ar' else f"❌ *Quiz generation failed*\n\n{esc(str(e))}"
        await safe_edit(query, msg, reply_markup=back_keyboard(lang))
        return

    if not questions:
        msg = "❌ لم يُولَّد أي سؤال صالح. حاول بمحتوى أطول." if lang == 'ar' else "❌ No valid questions generated."
        await safe_edit(query, msg, reply_markup=back_keyboard(lang))
        return

    # حفظ في قاعدة البيانات
    try:
        quiz_id = save_quiz(
            user_id,
            context.user_data.get('content_title', 'Quiz'),
            content,
            lang,
            difficulty,
            len(questions)
        )
        if not quiz_id:
            raise ValueError("Failed to save quiz")
        save_questions(quiz_id, questions)
    except Exception as e:
        logger.error(f"save quiz error: {e}", exc_info=True)
        msg = "❌ خطأ في حفظ الاختبار. حاول مجدداً." if lang == 'ar' else "❌ Error saving quiz."
        await safe_edit(query, msg, reply_markup=back_keyboard(lang))
        return

    context.user_data['current_quiz_id'] = quiz_id
    context.user_data['questions'] = questions
    context.user_data['state'] = None
    context.user_data['selected_types'] = ['multiple_choice', 'true_false', 'fill_blank', 'qa']

    # خصم نقطة واحدة
    remaining_points = None
    if user_id:
        desc = f"توليد اختبار ({len(questions)} سؤال)" if lang == 'ar' else f"Quiz generation ({len(questions)} questions)"
        remaining_points = update_user_points(user_id, -1, description=desc)

    # عرض النتيجة
    diff_ar = {'easy': 'سهل', 'medium': 'متوسط', 'hard': 'صعب'}
    diff_en = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}
    diff_label = diff_ar.get(difficulty, difficulty) if lang == 'ar' else diff_en.get(difficulty, difficulty)

    if lang == 'ar':
        points_note = f"\n\n💳 *تم خصم نقطة واحدة*\n💰 رصيدك: *{remaining_points:.1f}* نقطة" if remaining_points is not None else ""
        msg = f"✅ *تم توليد {len(questions)} سؤالاً بنجاح!*\n\n🎯 الصعوبة: {diff_label}\n🌍 اللغة: العربية{points_note}"
    else:
        points_note = f"\n\n💳 *1 point deducted*\n💰 Balance: *{remaining_points:.1f}* points" if remaining_points is not None else ""
        msg = f"✅ *{len(questions)} questions generated!*\n\n🎯 Difficulty: {diff_label}\n🌍 Language: English{points_note}"

    await safe_edit(query, msg, reply_markup=quiz_start_keyboard(quiz_id, lang))


async def start_quiz(query, context, db_user, lang, quiz_id):
    """بدء الاختبار"""
    questions = context.user_data.get('questions')
    if not questions or context.user_data.get('current_quiz_id') != quiz_id:
        questions_raw = get_quiz_questions(quiz_id)
        if not questions_raw:
            await safe_edit(query, "❌ لم يتم العثور على أسئلة." if lang == 'ar' else "❌ No questions found.", parse_mode=None)
            return
        questions = []
        for q in questions_raw:
            opts = None
            if q.get('options'):
                try:
                    opts = json.loads(q['options'])
                except Exception:
                    opts = None
            questions.append({
                'type': q['question_type'],
                'question': q['question_text'],
                'options': opts,
                'correct_answer': q['correct_answer'],
                'explanation': q.get('explanation', '')
            })
        context.user_data['questions'] = questions
        context.user_data['current_quiz_id'] = quiz_id

    context.user_data.update({
        'quiz_id': quiz_id,
        'user_id': db_user['user_id'],
        'current_q_idx': 0,
        'answers': [],
        'score': 0,
        'state': None,
    })

    await send_question(query, context, questions, 0, lang)


async def send_question(query_or_msg, context, questions, idx, lang):
    """إرسال سؤال للمستخدم"""
    if not questions or idx >= len(questions):
        await finish_quiz(query_or_msg, context, lang)
        return

    q = questions[idx]
    q_type = q.get('type', 'multiple_choice')
    total = len(questions)
    q_text = esc(q.get('question', ''))

    prog = f"📝 *السؤال {idx + 1} من {total}*\n\n" if lang == 'ar' else f"📝 *Question {idx + 1} of {total}*\n\n"
    full_text = prog + q_text

    is_query = hasattr(query_or_msg, 'edit_message_text')

    try:
        if q_type == 'multiple_choice' and q.get('options'):
            kb = mc_answer_keyboard(q['options'], idx)
            if is_query:
                await safe_edit(query_or_msg, full_text, reply_markup=kb)
            else:
                await safe_reply(query_or_msg, full_text, reply_markup=kb)

        elif q_type == 'true_false':
            kb = tf_answer_keyboard(idx, lang)
            if is_query:
                await safe_edit(query_or_msg, full_text, reply_markup=kb)
            else:
                await safe_reply(query_or_msg, full_text, reply_markup=kb)

        elif q_type == 'fill_blank':
            instr = "\n\n✏️ *اكتب إجابتك:*" if lang == 'ar' else "\n\n✏️ *Type your answer:*"
            context.user_data['state'] = 'answering_fill_blank'
            context.user_data['current_q_idx'] = idx
            if is_query:
                await safe_edit(query_or_msg, full_text + instr)
            else:
                await safe_reply(query_or_msg, full_text + instr)

        elif q_type == 'qa':
            instr = "\n\n✏️ *اكتب إجابتك التفصيلية:*" if lang == 'ar' else "\n\n✏️ *Write your answer:*"
            context.user_data['state'] = 'waiting_qa_answer'
            context.user_data['current_q_idx'] = idx
            if is_query:
                await safe_edit(query_or_msg, full_text + instr)
            else:
                await safe_reply(query_or_msg, full_text + instr)

        else:
            logger.warning(f"Unknown type '{q_type}'")
            context.user_data.setdefault('answers', []).append({
                'question': q.get('question', ''),
                'user_answer': '—',
                'correct_answer': q.get('correct_answer', ''),
                'is_correct': False
            })
            await send_question(query_or_msg, context, questions, idx + 1, lang)

    except Exception as e:
        logger.error(f"send_question error: {e}")
        err = "❌ خطأ في عرض السؤال." if lang == 'ar' else "❌ Error displaying question."
        if is_query:
            await safe_edit(query_or_msg, err, parse_mode=None)
        else:
            await safe_reply(query_or_msg, err, parse_mode=None)
        await asyncio.sleep(1)
        await send_question(query_or_msg, context, questions, idx + 1, lang)


async def handle_answer(query, context, lang, data):
    """معالجة إجابة المستخدم (أزرار)"""
    try:
        parts = data.split('_', 2)
        q_idx = int(parts[1])
        user_answer = parts[2]
    except (ValueError, IndexError):
        logger.error(f"Bad answer data: {data}")
        return

    questions = context.user_data.get('questions', [])
    if q_idx >= len(questions):
        return

    q = questions[q_idx]
    correct = q.get('correct_answer', '').strip()
    explanation = esc(q.get('explanation', ''))
    is_correct = user_answer.strip().lower() == correct.strip().lower()

    if is_correct:
        context.user_data['score'] = context.user_data.get('score', 0) + 1

    context.user_data.setdefault('answers', []).append({
        'question': q.get('question', ''),
        'user_answer': user_answer,
        'correct_answer': correct,
        'is_correct': is_correct
    })

    correct_safe = esc(correct)
    if is_correct:
        feedback = f"✅ *إجابة صحيحة!* 🎉\n\n💡 {explanation}" if lang == 'ar' else f"✅ *Correct!* 🎉\n\n💡 {explanation}"
    else:
        if lang == 'ar':
            feedback = f"❌ *إجابة خاطئة*\n\n✅ الإجابة الصحيحة: *{correct_safe}*\n\n💡 {explanation}"
        else:
            feedback = f"❌ *Wrong!*\n\n✅ Correct answer: *{correct_safe}*\n\n💡 {explanation}"

    next_idx = q_idx + 1
    context.user_data['current_q_idx'] = next_idx

    if next_idx >= len(questions):
        await safe_edit(query, feedback)
        await asyncio.sleep(1.2)
        await finish_quiz(query, context, lang)
    else:
        next_label = "➡️ السؤال التالي" if lang == 'ar' else "➡️ Next Question"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(next_label, callback_data=f"next_q_{next_idx}")]])
        await safe_edit(query, feedback, reply_markup=kb)


async def process_text_answer(update, context, user_answer: str, lang: str, is_fill_blank: bool):
    """معالجة الإجابة النصية (ملء فراغات أو سؤال مفتوح)"""
    questions = context.user_data.get('questions', [])
    idx = context.user_data.get('current_q_idx', 0)

    if not questions or idx >= len(questions):
        await safe_reply(update.message, "❌ انتهى الاختبار." if lang == 'ar' else "❌ Quiz ended.")
        context.user_data['state'] = None
        return

    q = questions[idx]
    correct = q.get('correct_answer', '').strip()
    explanation = esc(q.get('explanation', ''))
    correct_safe = esc(correct)

    if is_fill_blank:
        ua = user_answer.strip().lower()
        co = correct.lower()
        is_correct = (ua == co) or (ua in co) or (co in ua)
        if is_correct:
            context.user_data['score'] = context.user_data.get('score', 0) + 1
            feedback = f"✅ *إجابة صحيحة!* 🎉\n\n💡 {explanation}" if lang == 'ar' else f"✅ *Correct!* 🎉\n\n💡 {explanation}"
        else:
            if lang == 'ar':
                feedback = f"❌ *إجابة خاطئة*\n\n✅ الإجابة الصحيحة: *{correct_safe}*\n\n💡 {explanation}"
            else:
                feedback = f"❌ *Wrong!*\n\n✅ Correct answer: *{correct_safe}*\n\n💡 {explanation}"
    else:
        # تقييم السؤال المفتوح بالذكاء الاصطناعي
        try:
            loop = asyncio.get_event_loop()
            evaluation = await loop.run_in_executor(
                None, evaluate_qa_answer, q.get('question', ''), correct, user_answer, lang
            )
        except Exception as e:
            logger.error(f"QA evaluation error: {e}")
            evaluation = {"score": 50, "feedback": "تعذّر التقييم." if lang == 'ar' else "Could not evaluate."}

        score_pct = max(0, min(100, int(evaluation.get('score', 50))))
        fb_text = esc(evaluation.get('feedback', ''))
        is_correct = score_pct >= 60
        if is_correct:
            context.user_data['score'] = context.user_data.get('score', 0) + 1

        if lang == 'ar':
            feedback = f"📝 *تقييم إجابتك:*\n\n📊 النتيجة: *{score_pct}/100*\n💬 {fb_text}\n\n✅ الإجابة النموذجية: {correct_safe}"
        else:
            feedback = f"📝 *Answer Evaluation:*\n\n📊 Score: *{score_pct}/100*\n💬 {fb_text}\n\n✅ Model answer: {correct_safe}"

    context.user_data.setdefault('answers', []).append({
        'question': q.get('question', ''),
        'user_answer': user_answer,
        'correct_answer': correct,
        'is_correct': is_correct
    })
    context.user_data['state'] = None

    next_idx = idx + 1
    context.user_data['current_q_idx'] = next_idx
    await safe_reply(update.message, feedback)

    if next_idx >= len(questions):
        await asyncio.sleep(1)
        await finish_quiz(update.message, context, lang)
    else:
        await asyncio.sleep(0.3)
        await send_question(update.message, context, questions, next_idx, lang)


async def finish_quiz(query_or_msg, context, lang):
    """إنهاء الاختبار وعرض النتيجة"""
    questions = context.user_data.get('questions', [])
    score = context.user_data.get('score', 0)
    total = len(questions) or 1
    answers = context.user_data.get('answers', [])
    quiz_id = context.user_data.get('quiz_id')
    user_id = context.user_data.get('user_id')

    pct = round(score / total * 100, 1)

    if pct >= 90:
        grade = "🏆 ممتاز جداً!" if lang == 'ar' else "🏆 Outstanding!"
    elif pct >= 75:
        grade = "🥇 ممتاز!" if lang == 'ar' else "🥇 Excellent!"
    elif pct >= 60:
        grade = "👍 جيد!" if lang == 'ar' else "👍 Good!"
    elif pct >= 40:
        grade = "📚 يحتاج مراجعة" if lang == 'ar' else "📚 Needs Review"
    else:
        grade = "❗ ضعيف — راجع المادة" if lang == 'ar' else "❗ Weak — Review Material"

    # حفظ المحاولة
    if user_id and quiz_id:
        try:
            save_quiz_attempt(user_id, quiz_id, score, total, answers)
        except Exception as e:
            logger.error(f"save_quiz_attempt failed: {e}")

    if lang == 'ar':
        result = (f"🎯 *نتيجة الاختبار*\n\n✅ الإجابات الصحيحة: *{score}/{total}*\n📊 النسبة: *{pct}%*\n\n{grade}")
    else:
        result = (f"🎯 *Quiz Results*\n\n✅ Correct: *{score}/{total}*\n📊 Score: *{pct}%*\n\n{grade}")

    context.user_data['state'] = None
    is_query = hasattr(query_or_msg, 'edit_message_text')
    
    if is_query:
        await safe_edit(query_or_msg, result, reply_markup=back_keyboard(lang))
    else:
        await safe_reply(query_or_msg, result, reply_markup=back_keyboard(lang))


async def export_quiz_pdf(query, context, quiz_id: int, lang: str):
    """تصدير الأسئلة إلى PDF"""
    await safe_edit(query, "⏳ جاري إنشاء PDF..." if lang == 'ar' else "⏳ Creating PDF...", parse_mode=None)
    
    try:
        questions_raw = get_quiz_questions(quiz_id)
        if not questions_raw:
            await safe_edit(query, "❌ لا توجد أسئلة." if lang == 'ar' else "❌ No questions.", parse_mode=None)
            return

        title = context.user_data.get('content_title') or ('ملف الأسئلة' if lang == 'ar' else 'Quiz Questions')

        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(None, generate_quiz_pdf, list(questions_raw), title, lang)

        if not pdf_bytes:
            raise ValueError("PDF generation failed")

        file_obj = io.BytesIO(pdf_bytes)
        file_obj.name = f"quiz_{quiz_id}.pdf"

        caption = f"📄 <b>Quiz Questions PDF</b>\n\n✅ <b>{len(questions_raw)}</b> questions exported!" if lang == 'ar' else f"📄 <b>Quiz Questions PDF</b>\n\n✅ <b>{len(questions_raw)}</b> questions exported!"

        await query.message.reply_document(document=file_obj, filename=f"quiz_{quiz_id}.pdf", caption=caption, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"export_quiz_pdf error: {e}")
        await safe_edit(query, "❌ خطأ في إنشاء PDF." if lang == 'ar' else "❌ Error creating PDF.", parse_mode=None)


# ==================== دوال الأدمن ====================

async def handle_admin_actions(query, context, data: str):
    """معالجة أزرار لوحة التحكم"""
    if data == 'admin_stats':
        stats = get_stats()
        msg = (f"📊 *إحصائيات البوت*\n\n👥 المستخدمون: *{stats['total_users']}*\n📝 الاختبارات: *{stats['total_quizzes']}*\n🎯 المحاولات المكتملة: *{stats['total_attempts']}*")
        await safe_edit(query, msg, reply_markup=admin_keyboard())

    elif data == 'admin_users':
        users = get_all_users(15)
        if not users:
            lines = ["👥 *لا يوجد مستخدمون بعد.*"]
        else:
            lines = [f"👥 *آخر {len(users)} مستخدم:*\n"]
            for u in users:
                name = esc(u.get('first_name') or 'N/A')
                uname = f"@{esc(u['username'])}" if u.get('username') else '—'
                banned_tag = ' 🚫' if u.get('is_banned') else ''
                lines.append(f"• `{u['user_id']}` {name} {uname}{banned_tag}\n  محاولات: {u['attempts']} | نقاط: {float(u.get('points', 0)):.1f}")
        await safe_edit(query, '\n'.join(lines), reply_markup=admin_keyboard())

    elif data == 'admin_add_attempts':
        context.user_data['admin_action'] = 'add_attempts'
        context.user_data['state'] = 'waiting_admin_input'
        await safe_edit(query, "➕ *إضافة محاولات*\n\nأرسل بالصيغة:\n`user_id عدد`\n\nمثال: `123456 10`", reply_markup=back_keyboard('ar'))

    elif data == 'admin_set_attempts':
        context.user_data['admin_action'] = 'set_attempts'
        context.user_data['state'] = 'waiting_admin_input'
        await safe_edit(query, "⚙️ *تعيين محاولات*\n\nأرسل بالصيغة:\n`user_id عدد`", reply_markup=back_keyboard('ar'))

    elif data == 'admin_manage_points':
        context.user_data['admin_action'] = 'manage_points'
        context.user_data['state'] = 'waiting_admin_input'
        await safe_edit(query, "⭐ *إدارة النقاط*\n\nأرسل بالصيغة:\n`user_id نقاط`\n\nمثال للإضافة: `123456 5`", reply_markup=back_keyboard('ar'))

    elif data == 'admin_ban':
        context.user_data['admin_action'] = 'ban_user'
        context.user_data['state'] = 'waiting_admin_input'
        await safe_edit(query, "🚫 *حظر/رفع حظر*\n\nأرسل بالصيغة:\n`user_id ban` أو `user_id unban`", reply_markup=back_keyboard('ar'))

    elif data == 'admin_broadcast':
        context.user_data['admin_action'] = 'broadcast'
        context.user_data['state'] = 'waiting_admin_input'
        await safe_edit(query, "📢 *رسالة جماعية*\n\nاكتب الرسالة:", reply_markup=back_keyboard('ar'))


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخالات الأدمن"""
    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get('admin_action', '')
    text = update.message.text.strip()
    context.user_data['state'] = None
    context.user_data['admin_action'] = None

    try:
        if action == 'add_attempts':
            parts = text.split()
            uid = int(parts[0])
            amt = int(parts[1])
            new_val = update_user_attempts(uid, amt)
            if new_val is None:
                raise ValueError(f"المستخدم {uid} غير موجود")
            msg = f"✅ إضافة *{abs(amt)}* محاولة للمستخدم `{uid}`\nالمجموع: *{new_val}*"

        elif action == 'set_attempts':
            parts = text.split()
            uid = int(parts[0])
            amt = int(parts[1])
            if amt < 0:
                raise ValueError("العدد يجب أن يكون 0 أو أكثر")
            new_val = set_user_attempts(uid, amt)
            msg = f"✅ تم تعيين محاولات `{uid}` إلى *{new_val}*"

        elif action == 'manage_points':
            parts = text.split()
            uid = int(parts[0])
            pts = float(parts[1])
            new_val = update_user_points(uid, pts)
            label = "إضافة" if pts >= 0 else "خصم"
            msg = f"✅ {label} *{abs(pts):.1f}* نقطة للمستخدم `{uid}`\nالنقاط الجديدة: *{new_val:.1f}*"

        elif action == 'ban_user':
            parts = text.split()
            uid = int(parts[0])
            act = parts[1].lower()
            banned = act == 'ban'
            ok = ban_user(uid, banned)
            if not ok:
                raise ValueError(f"المستخدم {uid} غير موجود")
            status = "محظور" if banned else "مرفوع الحظر"
            msg = f"✅ المستخدم `{uid}` أصبح {status}"

        elif action == 'broadcast':
            all_users = get_all_users(limit=1000)
            sent = 0
            for u in all_users:
                if u.get('is_banned'):
                    continue
                try:
                    await context.bot.send_message(chat_id=u['user_id'], text=f"📢 *رسالة من الإدارة*\n\n{text}", parse_mode=MD)
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
            msg = f"✅ تم الإرسال لـ *{sent}* مستخدم"

        else:
            msg = "❌ إجراء غير معروف."

    except Exception as e:
        msg = f"❌ *خطأ:* {esc(str(e))}"

    await update.message.reply_text(msg, parse_mode=MD, reply_markup=admin_keyboard())


# ==================== معالج الأخطاء العام ====================

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    from telegram.error import Conflict, NetworkError, TimedOut

    err = context.error

    if isinstance(err, Conflict):
        logger.warning(f"Polling conflict: {err}")
        return

    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f"Network error: {err}")
        return

    logger.error(f"Unhandled error: {err}", exc_info=err)

    if isinstance(update, Update) and update.effective_message:
        try:
            lang = context.user_data.get('lang', 'ar') if context.user_data else 'ar'
            msg = "❌ حدث خطأ غير متوقع. اكتب /start للبدء من جديد." if lang == 'ar' else "❌ Unexpected error. Type /start to restart."
            await update.effective_message.reply_text(msg)
        except Exception:
            pass

async def cmd_key_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المفاتيح (للأدمن فقط)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    from api_key_manager import key_manager
    stats = key_manager.get_stats()
    
    msg = "🔑 *إحصائيات مفاتيح API*\n\n"
    for service, data in stats.items():
        msg += f"*{service.upper()}:*\n"
        msg += f"  📊 المجموع: {data['total']}\n"
        msg += f"  ✅ النشطة: {data['active']}\n"
        msg += f"  🔄 الاستخدام الكلي: {data['total_usage']}\n"
        msg += f"  📝 التفاصيل:\n"
        for k in data['keys']:
            status = "✅" if k['active'] else "❌"
            msg += f"    {status} {k['id']}: استخدام {k['usage']} | أخطاء {k['errors']}\n"
        msg += "\n"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# سجل الأمر في bot.py
app.add_handler(CommandHandler("keystats", cmd_key_stats))
