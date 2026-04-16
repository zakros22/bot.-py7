import os
import io
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
import textwrap

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

# توكن البوت
TOKEN = os.environ.get("BOT_TOKEN")

# تخزين مؤقت لآخر رسالة لكل مستخدم
user_last_message = {}

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل النص إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("🖼 تحويل النص إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("❓ مساعدة", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✨ أهلاً بك في البوت المتكامل! ✨\n\n"
        "أرسل لي أي نص، ثم اختر ما تريد فعله به:\n"
        "🎵 تحويل إلى صوت\n"
        "🖼 تحويل إلى صورة\n"
        "📊 تحليل النص\n\n"
        "أو استخدم الأزرار أدناه:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **طريقة الاستخدام:**\n\n"
        "1️⃣ أرسل أي نص تريد معالجته\n"
        "2️⃣ اختر من القائمة:\n"
        "   • 🎵 صوت - أحول النص إلى ملف MP3\n"
        "   • 🖼 صورة - أحول النص إلى صورة جميلة\n"
        "   • 📊 تحليل - أحلل النص وأعطيك معلومات عنه\n\n"
        "🔹 الأوامر المتاحة:\n"
        "/start - بدء البوت\n"
        "/help - هذه المساعدة\n"
        "/about - معلومات عن البوت",
        parse_mode="Markdown"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **بوت التحويل المتكامل**\n\n"
        "✅ تحويل النص إلى صوت (TTS)\n"
        "✅ تحويل النص إلى صورة\n"
        "✅ تحليل النص (عدد الحروف، الكلمات، الجمل)\n"
        "✅ واجهة أزرار تفاعلية\n\n"
        "🛠 التقنيات المستخدمة:\n"
        "- Python + python-telegram-bot\n"
        "- gTTS (تحويل النص لصوت)\n"
        "- PIL (تحويل النص لصورة)\n\n"
        "🎯 يعمل على Heroku بدون مشاكل!",
        parse_mode="Markdown"
    )

# ========== وظيفة تحويل النص إلى صوت ==========
async def text_to_audio(text: str, update: Update):
    try:
        # إنشاء ملف صوتي
        tts = gTTS(text=text, lang='ar')
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_buffer.name = "output.mp3"
        
        # إرسال الملف الصوتي
        await update.message.reply_audio(
            audio=audio_buffer,
            title="النص الصوتي",
            performer="البوت",
            caption=f"🎵 تم تحويل النص إلى صوت\n\nالنص: {text[:100]}..."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ في تحويل النص إلى صوت: {str(e)}")

# ========== وظيفة تحويل النص إلى صورة ==========
async def text_to_image(text: str, update: Update):
    try:
        # إعدادات الصورة
        img_width = 800
        img_height = 400
        background_color = (25, 25, 112)  # أزرق داكن
        text_color = (255, 255, 255)  # أبيض
        
        # إنشاء صورة جديدة
        img = Image.new('RGB', (img_width, img_height), color=background_color)
        draw = ImageDraw.Draw(img)
        
        # محاولة تحميل خط عربي (إذا لم يتوفر يستخدم الخط الافتراضي)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        # تقسيم النص الطويل إلى أسطر
        wrapped_text = textwrap.wrap(text, width=40)
        
        # رسم النص على الصورة
        y_start = 50
        for i, line in enumerate(wrapped_text):
            draw.text((50, y_start + i * 30), line, fill=text_color, font=font)
        
        # حفظ الصورة في الذاكرة
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "output.png"
        
        # إرسال الصورة
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 تم تحويل النص إلى صورة\n\nالنص: {text[:100]}..."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ في تحويل النص إلى صورة: {str(e)}")

# ========== وظيفة تحليل النص ==========
async def analyze_text(text: str, update: Update):
    # إحصائيات النص
    num_chars = len(text)
    num_words = len(text.split())
    num_sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
    num_spaces = text.count(' ')
    num_letters = sum(c.isalpha() for c in text)
    num_digits = sum(c.isdigit() for c in text)
    
    # تحليل المشاعر (بسيط)
    positive_words = ['حلو', 'جميل', 'رائع', 'ممتاز', 'سعيد', 'فرح', 'حب', 'جميلة']
    negative_words = ['سيء', 'حزين', 'صعب', 'صعبة', 'كئيب', 'مؤلم', 'غضب', 'كره']
    
    sentiment = "😊 إيجابي"
    for word in positive_words:
        if word in text.lower():
            sentiment = "😊 إيجابي"
            break
    for word in negative_words:
        if word in text.lower():
            sentiment = "😔 سلبي"
            break
    if "?" in text or "؟" in text:
        sentiment = "❓ استفهامي"
    
    # إنشاء تقرير التحليل
    analysis_report = (
        f"📊 **تحليل النص** 📊\n\n"
        f"📝 **النص الأصلي:**\n{text[:200]}{'...' if len(text) > 200 else ''}\n\n"
        f"📈 **الإحصائيات:**\n"
        f"• عدد الحروف: {num_chars}\n"
        f"• عدد الكلمات: {num_words}\n"
        f"• عدد الجمل: {num_sentences}\n"
        f"• عدد المسافات: {num_spaces}\n"
        f"• أحرف أبجدية: {num_letters}\n"
        f"• أرقام: {num_digits}\n\n"
        f"🎭 **تحليل المشاعر:** {sentiment}\n\n"
        f"📏 **طول النص:** {'قصير' if num_words < 10 else 'متوسط' if num_words < 30 else 'طويل'}"
    )
    
    await update.message.reply_text(analysis_report, parse_mode="Markdown")

# ========== معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    
    # تخزين آخر رسالة للمستخدم
    user_last_message[user_id] = user_text
    
    # عرض خيارات للمستخدم
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("🖼 تحويل إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("🔄 إرسال نص جديد", callback_data="new_text")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📩 **لقد أرسلت:**\n{user_text[:200]}{'...' if len(user_text) > 200 else ''}\n\n"
        f"🔽 **اختر ما تريد فعله بهذا النص:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ========== معالجة أزرار الاختيار ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data
    user_text = user_last_message.get(user_id, "")
    
    if not user_text:
        await query.edit_message_text(
            "❌ لم أجد أي نص سابق. الرجاء إرسال نص أولاً."
        )
        return
    
    if action == "to_audio":
        await query.edit_message_text("🎵 جاري تحويل النص إلى صوت... ⏳")
        await text_to_audio(user_text, update)
        await query.delete_message()
        
    elif action == "to_image":
        await query.edit_message_text("🖼 جاري تحويل النص إلى صورة... ⏳")
        await text_to_image(user_text, update)
        await query.delete_message()
        
    elif action == "analyze":
        await query.edit_message_text("📊 جاري تحليل النص... ⏳")
        await analyze_text(user_text, update)
        await query.delete_message()
        
    elif action == "new_text":
        await query.edit_message_text(
            "✏️ أرسل لي نصاً جديداً وسأقوم بمعالجته."
        )
        
    elif action == "help":
        await query.edit_message_text(
            "📖 **طريقة الاستخدام:**\n\n"
            "1️⃣ أرسل أي نص\n"
            "2️⃣ اختر من الأزرار:\n"
            "   • صوت 🎵 - أحوله إلى ملف MP3\n"
            "   • صورة 🖼 - أحوله إلى صورة\n"
            "   • تحليل 📊 - أحلله وأعطيك تقريراً\n\n"
            "للبدء، أرسل /start",
            parse_mode="Markdown"
        )

# ========== تشغيل البوت ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # تشغيل البوت
    print("🚀 البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
