# -*- coding: utf-8 -*-
import os
import logging
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
from langdetect import detect
from config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL, PORT

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب عند الضغط على /start"""
    await update.message.reply_text(
        "🎙️ *أهلاً بك في بوت تحويل النص إلى صوت!*\n\n"
        "📝 أرسل لي أي نص (طويل أو قصير) بأي لغة، وسأرسل لك ملفاً صوتياً.\n\n"
        "🌍 اللغات المدعومة: العربية، الإنجليزية، الفرنسية، الإسبانية، الهندية، وغيرها الكثير.\n\n"
        "⚠️ *ملاحظة:* البوت يحول النص المكتوب فقط، وليس الصور أو الملفات.",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة المساعدة"""
    await update.message.reply_text(
        "📖 *كيفية استخدام البوت:*\n\n"
        "1️⃣ أرسل أي نص مكتوب.\n"
        "2️⃣ انتظر قليلاً.\n"
        "3️⃣ استلم الملف الصوتي.\n\n"
        "🌐 اللغة تكتشف تلقائياً.\n"
        "📏 الحد الأقصى: 5000 حرف.\n\n"
        "👨‍💻 *للمطور:* هذا البوت يستخدم gTTS (Google Text-to-Speech).",
        parse_mode="Markdown"
    )


async def text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحويل النص المستلم إلى صوت"""
    user_text = update.message.text
    
    # التحقق من طول النص
    if len(user_text) > 5000:
        await update.message.reply_text(
            "⚠️ النص طويل جداً (أكثر من 5000 حرف).\n"
            "الرجاء إرسال نص أقصر أو تقسيمه إلى أجزاء."
        )
        return
    
    # إرسال رسالة مؤقتة
    wait_msg = await update.message.reply_text("🎤 جاري تحويل النص إلى صوت...")
    
    try:
        # 1. اكتشاف لغة النص تلقائياً
        try:
            lang = detect(user_text)
        except:
            # إذا فشل اكتشاف اللغة، نستخدم العربية كلغة افتراضية
            lang = "ar"
        
        # 2. تحويل النص إلى صوت في الذاكرة
        mp3_buffer = io.BytesIO()
        tts = gTTS(text=user_text, lang=lang, slow=False)
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)
        
        # 3. حذف رسالة "جاري التحويل"
        await wait_msg.delete()
        
        # 4. إرسال الملف الصوتي مع اسم مناسب
        filename = f"voice_{update.effective_user.id}.mp3"
        await update.message.reply_audio(
            audio=mp3_buffer,
            filename=filename,
            caption=f"✅ تم تحويل النص إلى صوت!\n🌐 اللغة: {lang}\n📝 عدد الأحرف: {len(user_text)}",
            title="النص المحول",
            performer="Text-to-Speech Bot"
        )
        
    except Exception as e:
        await wait_msg.delete()
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء التحويل:\n`{str(e)[:100]}`\n\n"
            "الرجاء المحاولة مرة أخرى أو التأكد من صحة النص.",
            parse_mode="Markdown"
        )
        logger.error(f"Error converting text: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """البوت لا يدعم تحويل الصوت إلى نص"""
    await update.message.reply_text(
        "⚠️ هذا البوت يحول *النص المكتوب* إلى *صوت* فقط.\n"
        "أرسل نصاً مكتوباً وليس رسالة صوتية.",
        parse_mode="Markdown"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """البوت لا يدعم الملفات"""
    await update.message.reply_text(
        "⚠️ هذا البوت يحول *النص المكتوب* فقط.\n"
        "أرسل النص مباشرة في الرسالة، وليس كملف.",
        parse_mode="Markdown"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأخطاء العامة"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """تشغيل البوت"""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة")
    
    # إنشاء التطبيق
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_to_speech))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 البوت جاهز للعمل...")
    
    # تشغيل البوت (Webhook أو Polling)
    if WEBHOOK_URL:
        # وضع Webhook (لـ Heroku)
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook"
        )
        logger.info(f"✅ Webhook mode active on port {PORT}")
    else:
        # وضع Polling (للتطوير المحلي)
        application.run_polling()
        logger.info("✅ Polling mode active")


if __name__ == "__main__":
    main()
