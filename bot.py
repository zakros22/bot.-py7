import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
from langdetect import detect
import io

# إعدادات التسجيل (عشان تشوف الأخطاء)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ضع توكن البوت الخاص بك هنا (من BotFather)
TOKEN = "ضع_توكن_البوت_هنا"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    await update.message.reply_text(
        "🎙️ أهلاً بك في بوت تحويل النص إلى صوت!\n\n"
        "📝 أرسل لي أي نص (طويل أو قصير) بأي لغة، وسأرسل لك ملفاً صوتياً.\n\n"
        "🌍 اللغات المدعومة: العربية، الإنجليزية، الفرنسية، الإسبانية، الهندية، وغيرها الكثير."
    )

async def text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحويل النص المستلم إلى صوت"""
    user_text = update.message.text
    
    # رسالة مؤقتة
    wait_msg = await update.message.reply_text("🎤 جاري تحويل النص إلى صوت...")
    
    try:
        # 1. اكتشاف لغة النص تلقائياً
        lang = detect(user_text)
        
        # 2. تحويل النص إلى صوت في الذاكرة (بدون حفظ ملف)
        mp3_buffer = io.BytesIO()
        tts = gTTS(text=user_text, lang=lang, slow=False)
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)  # الرجوع لأول الملف
        
        # 3. حذف رسالة "جاري التحويل"
        await wait_msg.delete()
        
        # 4. إرسال الملف الصوتي
        await update.message.reply_voice(
            voice=mp3_buffer,
            caption=f"✅ تم التحويل!\n🌐 اللغة المكتشفة: {lang}"
        )
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ حدث خطأ: {str(e)[:50]}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """البوت لا يدعم تحويل الصوت إلى نص (فقط للتوضيح)"""
    await update.message.reply_text("⚠️ هذا البوت يحول *النص* إلى *صوت* فقط. أرسل نصاً مكتوباً.")

def main():
    """تشغيل البوت"""
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_to_speech))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))  # اختياري
    
    print("🤖 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
