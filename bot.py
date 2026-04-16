import os
import io
import logging
import urllib.parse
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from PIL import Image, ImageDraw, ImageFont
import textwrap

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين آخر رسالة لكل مستخدم
user_last_message = {}

# ========== تحويل النص إلى صوت (بديل مجاني يعمل) ==========
async def text_to_audio_simple(text: str, update: Update):
    try:
        text_encoded = urllib.parse.quote(text[:200])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl=ar&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            audio_data = response.read()
        
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "voice.mp3"
        
        await update.message.reply_audio(
            audio=audio_file,
            title="النص الصوتي",
            performer="Google TTS",
            caption=f"تم تحويل النص إلى صوت"
        )
    except Exception as e:
        await update.message.reply_text("عذرا، خدمة تحويل الصوت غير متاحة حاليا. حاول بنص أقصر.")

# ========== تحويل النص إلى صورة ==========
async def text_to_image_simple(text: str, update: Update):
    try:
        img = Image.new('RGB', (800, 400), color=(30, 30, 60))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        lines = textwrap.wrap(text, width=45)
        y = 50
        for line in lines:
            draw.text((40, y), line, fill=(255, 255, 255), font=font)
            y += 35
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "text_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"نصك على صورة"
        )
    except Exception as e:
        await update.message.reply_text(f"خطأ في إنشاء الصورة: {str(e)}")

# ========== تحليل النص ==========
async def analyze_text(text: str, update: Update):
    words = text.split()
    sentences_count = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
    
    report_text = f"""
📊 تحليل النص

📝 النص: {text[:150]}

📈 الإحصائيات:
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {sentences_count}
• عدد المسافات: {text.count(' ')}

📏 الطول: {'قصير' if len(words) < 15 else 'طويل'}
"""
    await update.message.reply_text(report_text)

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("تحويل إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("تحويل إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("تحليل النص", callback_data="analyze")],
    ]
    await update.message.reply_text(
        "أهلا بك في البوت\n\n"
        "أرسل لي أي نص ثم اختر من الأزرار:\n"
        "- صوت: يحول النص إلى ملف MP3\n"
        "- صورة: يحول النص إلى صورة\n"
        "- تحليل: يحلل النص ويعطيك معلومات عنه",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "كيفية الاستخدام:\n"
        "1. أرسل أي نص\n"
        "2. اضغط على الزر المناسب\n"
        "الأوامر المتاحة:\n"
        "/start - بدء البوت\n"
        "/help - المساعدة"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    user_last_message[user_id] = user_text
    
    keyboard = [
        [InlineKeyboardButton("تحويل إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("تحويل إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("تحليل النص", callback_data="analyze")],
    ]
    
    await update.message.reply_text(
        f"تم استلام نصك:\n\n{user_text[:200]}\n\nاختر ما تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data
    user_text = user_last_message.get(user_id, "")
    
    if not user_text:
        await query.edit_message_text("الرجاء إرسال نص أولا باستخدام /start")
        return
    
    await query.edit_message_text("جاري المعالجة...")
    
    if action == "to_audio":
        await text_to_audio_simple(user_text, update)
    elif action == "to_image":
        await text_to_image_simple(user_text, update)
    elif action == "analyze":
        await analyze_text(user_text, update)
    
    await query.delete_message()

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("البوت يعمل الآن على Heroku")
    app.run_polling()

if __name__ == "__main__":
    main()
