import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# تفعيل logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# قراءة التوكن من متغيرات البيئة
TOKEN = os.environ.get("BOT_TOKEN")

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً! أنا بوت يعمل على Heroku 🚀\n"
        "أرسل /help لمعرفة الأوامر المتاحة."
    )

# أمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 الأوامر المتاحة:\n"
        "/start - بدء البوت\n"
        "/help - عرض المساعدة\n"
        "/about - معلومات عن البوت"
    )

# أمر /about
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 هذا بوت تلغرام بسيط\n"
        "يعمل على Heroku باستخدام Polling\n"
        "🛠 تم إنشاؤه باستخدام python-telegram-bot"
    )

# الرد على الرسائل النصية العادية
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text(f"لقد كتبت: {user_text}")

# الرد على الرسائل التي تحتوي على صور
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تسلم، صورة جميلة!")

# دالة الخطأ
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"حدث خطأ: {context.error}")

# التشغيل الرئيسي
def main():
    print("جاري تشغيل البوت...")
    
    # إنشاء التطبيق
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة معالج الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    
    # إضافة معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    # إضافة معالج الأخطاء
    app.add_error_handler(error_handler)
    
    # 🔽 **هذا هو التعديل الوحيد** 🔽
    # بدلاً من start_webhook، استخدمنا start_polling
    app.run_polling()
    
    print("البوت توقف عن العمل.")

if __name__ == "__main__":
    main()
