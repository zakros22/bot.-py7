import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين بيانات المستخدمين
user_data = {}

# ========== البديل 1: Google Translate TTS (مجاني، يدعم كل اللغات) ==========
async def google_tts(text: str, lang: str, gender: str, update: Update):
    """Google TTS - يدعم 100+ لغة"""
    try:
        # تحديد اللغة
        lang_map = {
            'ar': 'ar', 'en': 'en', 'fr': 'fr', 'de': 'de', 'es': 'es',
            'it': 'it', 'tr': 'tr', 'ru': 'ru', 'zh': 'zh-CN', 'ja': 'ja'
        }
        lang_code = lang_map.get(lang, 'ar')
        
        text_encoded = urllib.parse.quote(text[:200])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang_code}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            audio_data = response.read()
        
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "google_tts.mp3"
        
        await update.message.reply_audio(
            audio=audio_file,
            title="Google TTS",
            performer=f"{gender} | {lang}",
            caption=f"✅ تم التحويل بنجاح\n📝 النص: {text[:100]}..."
        )
        return True
    except Exception as e:
        logging.error(f"Google TTS error: {e}")
        return False

# ========== البديل 2: VoiceRSS API (مجاني، يدعم ذكر/أنثى) ==========
async def voicerss_tts(text: str, lang: str, gender: str, update: Update):
    """VoiceRSS - يدعم ذكر وأنثى"""
    try:
        # VoiceRSS API key (مجاني)
        api_key = "bc0b5b2b0b1b4b0b8b0b0b0b0b0b0b0"
        
        # تحديد الصوت حسب الجنس
        voice_map = {
            'male_ar': 'Youssef',
            'female_ar': 'Amina',
            'male_en': 'John',
            'female_en': 'Linda',
            'male_fr': 'Thomas',
            'female_fr': 'Julie'
        }
        
        voice_key = f"{gender}_{lang}"
        voice = voice_map.get(voice_key, 'Youssef' if gender == 'male' else 'Amina')
        
        params = {
            "key": api_key,
            "hl": lang,
            "src": text[:300],
            "f": "44khz_16bit_stereo",
            "c": "MP3",
            "v": voice
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get("http://api.voicerss.org/", params=params) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    if len(audio_data) > 1000:  # تأكد أن الملف صالح
                        audio_file = io.BytesIO(audio_data)
                        audio_file.name = "voicerss.mp3"
                        
                        await update.message.reply_audio(
                            audio=audio_file,
                            title="VoiceRSS TTS",
                            performer=f"{gender} | {lang}",
                            caption=f"✅ تم التحويل (VoiceRSS)\n📝 {text[:100]}..."
                        )
                        return True
        return False
    except Exception as e:
        logging.error(f"VoiceRSS error: {e}")
        return False

# ========== البديل 3: TTS API مجاني آخر ==========
async def tts_api_free(text: str, lang: str, gender: str, update: Update):
    """TTS API مجاني - STT"""
    try:
        # استخدام خدمة STT TTS المجانية
        text_encoded = urllib.parse.quote(text[:200])
        url = f"https://api.streamelements.com/kappa/v2/speech?voice={gender}&text={text_encoded}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            audio_data = response.read()
        
        if len(audio_data) > 1000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "stream_tts.mp3"
            
            await update.message.reply_audio(
                audio=audio_file,
                title="Stream TTS",
                performer=f"{gender}",
                caption=f"✅ تم التحويل\n📝 {text[:100]}..."
            )
            return True
        return False
    except Exception as e:
        logging.error(f"Stream TTS error: {e}")
        return False

# ========== البديل 4: Text-to-Speech مجاني (رئيسي) ==========
async def text_to_speech_full(text: str, update: Update, lang: str = 'ar', gender: str = 'female'):
    """وظيفة رئيسية تحاول كل البدائل حتى تنجح"""
    
    # إرسال رسالة المعالجة
    processing_msg = await update.message.reply_text("🎙 جاري تحويل النص إلى صوت... (0% -> 100%)")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("🎙 معالجة النص وتحليله... (25%)")
    
    # تنظيف النص
    text = text.strip()
    if len(text) > 500:
        text = text[:500]
        await processing_msg.edit_text("🎙 تم تقصير النص إلى 500 حرف... (50%)")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("🎙 جاري الاتصال بخدمة الصوت... (75%)")
    
    # تجربة البدائل بالترتيب
    success = False
    
    # البديل 1: Google TTS
    if not success:
        await processing_msg.edit_text("🎙 تجربة Google TTS... (80%)")
        success = await google_tts(text, lang, gender, update)
    
    # البديل 2: VoiceRSS
    if not success:
        await processing_msg.edit_text("🎙 تجربة VoiceRSS... (90%)")
        success = await voicerss_tts(text, lang, gender, update)
    
    # البديل 3: Stream TTS
    if not success:
        await processing_msg.edit_text("🎙 تجربة Stream TTS... (95%)")
        success = await tts_api_free(text, lang, gender, update)
    
    if success:
        await processing_msg.delete()
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح 100%")
    else:
        await processing_msg.edit_text("❌ عذراً، جميع خدمات الصوت غير متاحة حالياً. حاول بنص أقصر أو لاحقاً.")

# ========== تحويل النص إلى صورة (مع اختيار الطول أو العرض) ==========
async def text_to_image_full(text: str, update: Update, image_type: str = 'width'):
    """تحويل النص إلى صورة - طول أو عرض"""
    
    processing_msg = await update.message.reply_text("🖼 جاري تحويل النص إلى صورة... (0% -> 100%)")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("🖼 معالجة النص وتحضيره... (25%)")
    
    # تنظيف النص
    text = text.strip()
    if len(text) > 500:
        text = text[:500]
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("🖼 إنشاء الصورة... (50%)")
    
    try:
        # تحديد أبعاد الصورة حسب اختيار المستخدم
        if image_type == 'width':
            img_width = 1000
            img_height = 400
        else:  # طولي
            img_width = 600
            img_height = 800
        
        # ألوان عشوائية جميلة
        colors = [
            ((25, 25, 112), (255, 255, 255)),   # أزرق داكن - أبيض
            ((60, 20, 80), (255, 215, 0)),      # بنفسجي - ذهبي
            ((0, 100, 0), (255, 255, 255)),     # أخضر داكن - أبيض
            ((139, 0, 0), (255, 255, 255)),     # أحمر داكن - أبيض
            ((0, 0, 139), (255, 255, 255)),     # أزرق ملكي - أبيض
        ]
        bg_color, text_color = random.choice(colors)
        
        # إنشاء الصورة
        img = Image.new('RGB', (img_width, img_height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # محاولة استخدام خط أفضل
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 28)
            except:
                font = ImageFont.load_default()
        
        await processing_msg.edit_text("🖼 كتابة النص على الصورة... (75%)")
        
        # حساب عرض السطر حسب عرض الصورة
        chars_per_line = img_width // 22
        lines = textwrap.wrap(text, width=chars_per_line)
        
        # حساب المسافات
        line_height = 40
        total_height = len(lines) * line_height
        y_start = (img_height - total_height) // 2
        
        # رسم النص
        y = y_start
        for line in lines:
            # حساب عرض النص لتوسيطه
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
            except:
                text_width = len(line) * 20
            
            x = (img_width - text_width) // 2
            draw.text((x, y), line, fill=text_color, font=font)
            y += line_height
        
        await processing_msg.edit_text("🖼 حفظ وإرسال الصورة... (90%)")
        
        # حفظ الصورة
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG', quality=95)
        img_buffer.seek(0)
        img_buffer.name = "text_image.png"
        
        # إرسال الصورة
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 تم تحويل النص إلى صورة\n📏 النوع: {'عرضي' if image_type == 'width' else 'طولي'}\n📝 {text[:100]}..."
        )
        
        await processing_msg.delete()
        await update.message.reply_text("✅ تم تحويل النص إلى صورة بنجاح 100%")
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ خطأ في إنشاء الصورة: {str(e)}")

# ========== تحليل النص المتقدم ==========
async def analyze_text_full(text: str, update: Update):
    """تحليل كامل للنص"""
    
    msg = await update.message.reply_text("📊 جاري تحليل النص...")
    
    # اكتشاف اللغة
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_english = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_arabic and has_english:
        detected_lang = "عربي + إنجليزي (مختلط)"
        lang_code = 'ar'
    elif has_arabic:
        detected_lang = "عربي"
        lang_code = 'ar'
    else:
        detected_lang = "إنجليزي / أخرى"
        lang_code = 'en'
    
    # إحصائيات
    words = text.split()
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟') + text.count('،')
    
    report = f"""
📊 **تحليل النص الكامل**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:200]}{'...' if len(text) > 200 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📈 **الإحصائيات:**

• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {sentences}
• عدد المسافات: {text.count(' ')}
• عدد الأرقام: {sum(c.isdigit() for c in text)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة المكتشفة:** {detected_lang}

📏 **طول النص:** {'قصير جداً' if len(words) < 5 else 'قصير' if len(words) < 15 else 'متوسط' if len(words) < 30 else 'طويل'}

✅ تم التحليل بنجاح
"""
    
    await msg.edit_text(report)

# ========== أزرار البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل إلى صوت", callback_data="audio_menu")],
        [InlineKeyboardButton("🖼 تحويل إلى صورة", callback_data="image_menu")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
    ]
    
    await update.message.reply_text(
        "✨ **بوت التحويل المتكامل 100%** ✨\n\n"
        "📤 **أرسل لي أي نص** (أي لغة)\n\n"
        "ثم اختر:\n"
        "🎵 → يحول النص إلى صوت MP3 (اختيار ذكر/أنثى)\n"
        "🖼 → يحول النص إلى صورة (اختيار طولي/عرضي)\n"
        "📊 → يحلل النص بالكامل\n\n"
        "✅ **مجاني 100% - يعمل على Heroku**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    keyboard = [
        [InlineKeyboardButton("👨 ذكر - عربي", callback_data=f"audio|ar|male|{user_text[:100]}")],
        [InlineKeyboardButton("👩 أنثى - عربي", callback_data=f"audio|ar|female|{user_text[:100]}")],
        [InlineKeyboardButton("👨 ذكر - إنجليزي", callback_data=f"audio|en|male|{user_text[:100]}")],
        [InlineKeyboardButton("👩 أنثى - إنجليزي", callback_data=f"audio|en|female|{user_text[:100]}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    
    await update.callback_query.edit_message_text(
        f"🎵 **اختر نوع الصوت:**\n\n"
        f"📝 النص: {user_text[:150]}...\n\n"
        f"🔊 اختر اللغة والجنس:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def image_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    keyboard = [
        [InlineKeyboardButton("📐 عرضي (أفقي)", callback_data=f"image|width|{user_text[:100]}")],
        [InlineKeyboardButton("📏 طولي (عمودي)", callback_data=f"image|height|{user_text[:100]}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    
    await update.callback_query.edit_message_text(
        f"🖼 **اختر شكل الصورة:**\n\n"
        f"📝 النص: {user_text[:150]}...\n\n"
        f"اختر:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # تخزين النص
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['last_text'] = user_text
    
    # عرض القائمة
    keyboard = [
        [InlineKeyboardButton("🎵 تحويل إلى صوت", callback_data="main_audio")],
        [InlineKeyboardButton("🖼 تحويل إلى صورة", callback_data="main_image")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="main_analyze")],
    ]
    
    await update.message.reply_text(
        f"✅ **تم استلام نصك:**\n\n"
        f"\"{user_text[:200]}{'...' if len(user_text) > 200 else ''}\"\n\n"
        f"🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== معالجة الأزرار ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # الحصول على آخر نص للمستخدم
    last_text = user_data.get(user_id, {}).get('last_text', '')
    
    if data == "main_audio" and last_text:
        await audio_menu(update, context, last_text)
    elif data == "main_image" and last_text:
        await image_menu(update, context, last_text)
    elif data == "main_analyze" and last_text:
        await analyze_text_full(last_text, update)
        await query.delete_message()
    elif data == "back":
        await start(update, context)
        await query.delete_message()
    elif data.startswith("audio|"):
        parts = data.split("|")
        if len(parts) >= 4:
            lang = parts[1]
            gender = parts[2]
            text = parts[3]
            await text_to_speech_full(text, update, lang, gender)
            await query.delete_message()
    elif data.startswith("image|"):
        parts = data.split("|")
        if len(parts) >= 3:
            img_type = parts[1]
            text = parts[2]
            await text_to_image_full(text, update, img_type)
            await query.delete_message()

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ البوت يعمل على Heroku - النسخة الكاملة")
    app.run_polling()

if __name__ == "__main__":
    main()
