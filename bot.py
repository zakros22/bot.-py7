import os
import logging
import urllib.request
import shutil
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, PreCheckoutQueryHandler
from telegram.constants import ParseMode

from database import init_db, add_payment
from handlers import (
    cmd_start, cmd_menu, cmd_admin, cmd_lang,
    handle_text_input, handle_pdf, handle_callback,
    handle_next_question, global_error_handler
)
from api_key_manager import key_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables!")

PORT = int(os.environ.get("PORT", 8080))
ADMIN_ID = 7021542402  # ضع معرف حسابك هنا


def ensure_fonts():
    """تحميل خط Amiri للغة العربية في PDF"""
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    reg_path = os.path.join(fonts_dir, "Amiri-Regular.ttf")
    bold_path = os.path.join(fonts_dir, "Amiri-Bold.ttf")
    
    if not os.path.exists(reg_path):
        try:
            logger.info("Downloading Amiri-Regular.ttf...")
            urllib.request.urlretrieve(
                "https://fonts.gstatic.com/s/amiri/v27/J7aRnpd8CGxBHqUpvrIw74NL.ttf",
                reg_path,
            )
            logger.info("Amiri-Regular.ttf downloaded.")
        except Exception as e:
            logger.warning(f"Could not download Amiri font: {e}")
    
    if not os.path.exists(bold_path) and os.path.exists(reg_path):
        shutil.copy(reg_path, bold_path)


async def pre_checkout_handler(update: Update, context):
    """معالجة الدفع المسبق"""
    try:
        await update.pre_checkout_query.answer(ok=True)
    except Exception as e:
        logger.error(f"pre_checkout_handler error: {e}")


async def successful_payment_handler(update: Update, context):
    """معالجة الدفع الناجح"""
    try:
        payment = update.message.successful_payment
        user_id = update.effective_user.id
        stars = payment.total_amount
        attempts_to_add = max(1, (stars // 5) * 10)
        add_payment(user_id, stars, "telegram_stars", attempts_to_add, "confirmed")
        lang = context.user_data.get("lang", "ar")
        
        if lang == 'ar':
            msg = (f"✅ *تم الدفع بنجاح!*\n\n"
                   f"⭐ {stars} نجوم = *+{attempts_to_add} محاولة*\n\n"
                   f"شكراً لدعمك! 🎉")
        else:
            msg = (f"✅ *Payment Successful!*\n\n"
                   f"⭐ {stars} Stars = *+{attempts_to_add} attempts*\n\n"
                   f"Thank you! 🎉")
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"successful_payment_handler error: {e}")


async def handle_non_pdf(update: Update, context):
    """معالجة الملفات غير PDF"""
    lang = context.user_data.get("lang", "ar")
    if lang == 'ar':
        msg = "❌ نوع الملف غير مدعوم. أرسل ملف *PDF* فقط، أو الصق النص مباشرة."
    else:
        msg = "❌ File type not supported. Please send a *PDF* file, or paste text directly."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_keystats(update: Update, context):
    """عرض إحصائيات المفاتيح (للمطور فقط)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر للمطور فقط.")
        return
    
    stats = key_manager.get_stats()
    msg = "🔑 *إحصائيات مفاتيح API*\n\n"
    
    has_keys = False
    for service, data in stats.items():
        if data['total'] > 0:
            has_keys = True
            msg += f"📌 *{service.upper()}:*\n"
            msg += f"   ✅ النشطة: {data['active']}/{data['total']}\n"
            msg += f"   📊 الاستخدام الكلي: {data['total_usage']}\n"
            # عرض تفاصيل كل مفتاح
            for k in data['keys']:
                status = "✅" if k['active'] else "❌"
                msg += f"   {status} {k['id']}: {k['usage']} استخدام, {k['errors']} أخطاء\n"
            msg += "\n"
    
    if not has_keys:
        msg += "⚠️ لا توجد مفاتيح API مضافة!\n\n"
        msg += "أضف متغيرات مثل:\n"
        msg += "• OPENAI_API_KEYS\n"
        msg += "• GEMINI_API_KEYS\n"
        msg += "• GROQ_API_KEYS\n"
        msg += "• DEEPSEEK_API_KEYS\n"
        msg += "• OPENROUTER_API_KEYS\n\n"
        msg += "كل متغير يحتوي على مفاتيح مفصولة بفواصل:\n"
        msg += "`مفتاح1,مفتاح2,مفتاح3`"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


def main():
    # تجهيز الخطوط
    ensure_fonts()
    
    # تهيئة قاعدة البيانات
    logger.info("Initializing database...")
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        raise
    
    # بناء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ========== إضافة الأوامر ==========
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("help", cmd_menu))
    app.add_handler(CommandHandler("keystats", cmd_keystats))  # أمر إحصائيات المفاتيح
    
    # ========== معالجة الملفات ==========
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.PDF, handle_non_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # ========== معالجة الأزرار ==========
    app.add_handler(CallbackQueryHandler(handle_next_question, pattern=r"^next_q_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # ========== معالجة الدفع ==========
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # ========== معالجة الأخطاء ==========
    app.add_error_handler(global_error_handler)
    
    # تشغيل البوت
    logger.info("Starting bot in polling mode on Heroku...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "pre_checkout_query"]
    )


if __name__ == "__main__":
    main()
