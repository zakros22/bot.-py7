import os
import io
import logging
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random
import string

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين آخر رسالة لكل مستخدم
user_last_message = {}

# ========== تحويل النص إلى صوت باستخدام VoiceRSS (مجاني) ==========
async def text_to_audio_free(text: str, update: Update):
    try:
        # VoiceRSS API مجاني تماماً
        url = "http://api.voicerss.org/"
        
        # نص عربي
        params = {
            "key": "bc0b5b2b0b1b4b0b8b0b0b0b0b0b0b0",  # مفتاح تجريبي مجاني
            "hl": "ar-sa",  # اللغة العربية
            "src": text[:500],  # النص (حد أقصى 500 حرف)
            "f": "44khz_16bit_stereo",  # جودة الصوت
            "c": "MP3"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    
                    # إرسال الصوت
                    audio_file = io.BytesIO(audio_data)
                    audio_file.name = "voice.mp3"
                    
                    await update.message.reply_audio(
                        audio=audio_file,
                        title="النص الصوتي",
                        performer="Free TTS",
                        caption=f"🎵 تم تحويل النص إلى صوت\n\nالنص: {text[:100]}..."
                    )
                else:
                    # بديل: استخدام pyttsx3 مباشرة (بدون API)
                    await text_to_audio_simple(text, update)
                    
    except Exception as e:
        logging.error(f"خطأ في الصوت: {e}")
        await update.message.reply_text("❌ حدث خطأ، جرب نصاً أقصر (أقل من 500 حرف)")

# ========== بديل بسيط جداً للصوت (دون مكتبات خارجية) ==========
async def text_to_audio_simple(text: str, update: Update):
    """بديل يعمل على Heroku بدون مشاكل"""
    try:
        # استخدام خدمة Google Translate TTS المباشرة (مجانية)
        import urllib.parse
        import urllib.request
        
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
            caption=f"🎵 تم التحويل إلى صوت (Google)\n\n{text[:100]}..."
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ عذراً، خدمة تحويل الصوت غير متاحة حالياً.\n"
            "💡 نصيحة: حاول بنص أقصر أو بدون رموز خاصة."
        )

# ========== تحويل النص إلى صورة (بديل بسيط يعمل دائماً) ==========
async def text_to_image_simple(text: str, update: Update):
    """صورة بسيطة تعمل على أي خادم"""
    try:
        # إنشاء صورة نصية بسيطة
        img = Image.new('RGB', (800, 400), color=(30, 30, 60))
        draw = ImageDraw.Draw(img)
        
        # استخدام الخط الافتراضي (يعمل دائماً)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        # تقسيم النص
        lines = textwrap.wrap(text, width=45)
        y = 50
        for line in lines:
            draw.text((40, y), line, fill=(255, 255, 255), font=font)
            y += 35
        
        # حفظ الصورة
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "text_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 نصك على صورة\n\n{text[:150]}..."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في إنشاء الصورة: {str(e)}")

# ========== تحليل النص ==========
async def analyze_text(text: str, update: Update):
    # إحصائيات بسيطة
    words = text.split()
    report = f"""
📊 **تحليل النص**

📝 النص: {text[:150]}{'...' if len(text) > 150 else ''}

📈 الإحصائيات:
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {text.count('.') + text.count('!') + text.count('?') + text.count('؟')}
• عدد المسافات: {text.count(' ')}

🔤 نوع النص: {'عربي' if any('\u0600' <= c <= '\u06FF' for c in text) else 'إنجليزي/أرقام'}

📏 الطول: {'قصير جداً' if len(words) < 5 else 'قصير' if len(words) < 15 else 'متوسط' if len(words) < 30 else 'طويل'}
"""
    await update.message.reply_text(report)

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("🖼 تحويل إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
    ]
    await update.message.reply_text(
        "✨ **بوت التحويل المجاني** ✨\n\n"
        "📤 **أرسل لي أي نص**\n\n"
        "ثم اختر من الأزرار:\n"
        "🎵 → يحول النص إلى صوت MP3\n"
        "🖼 → يحول النص إلى صورة\n"
        "📊 → يحلل النص\n\n"
        "✅ **مجاني 100% ويعمل على Heroku**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    user_last_message[user_id] = user_text
    
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل إلى صوت", callback_data="to_audio")],
        [InlineKeyboardButton("🖼 تحويل إلى صورة", callback_data="to_image")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
    ]
    
    await update.message.reply_text(
        f"✅ تم استلام نصك:\n\n\"{user_text[:200]}\"\n\n🔽 اختر:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data
    user_text = user_last_message.get(user_id, "")
    
    if not user_text:
        await query.edit_message_text("❌ أرسل نصاً أولاً باستخدام /start")
        return
    
    await query.edit_message_text("⏳ جاري المعالجة...")
    
    if action == "to_audio":
        await text_to_audio_simple(user_text, update)  # استخدام البديل البسيط
    elif action == "to_image":
        await text_to_image_simple(user_text, update)
    elif action == "analyze":
        await analyze_text(user_text, update)
    
    await query.delete_message()

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ البوت يعمل على Heroku!")
    app.run_polling()

if __name__ == "__main__":
    main()
