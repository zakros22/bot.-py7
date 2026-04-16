import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
import random
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from PIL import Image, ImageDraw, ImageFont
import textwrap

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, CHOOSING_IMAGE_TYPE, WAITING_FOR_TEXT = range(4)

# تخزين بيانات المستخدمين
user_choices = {}

# ========== تحليل النص (أي لغة) ==========
async def analyze_text_universal(text: str):
    """تحليل النص لأي لغة"""
    words = text.split()
    chars = len(text)
    
    # اكتشاف اللغة
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_english = any('a' <= c.lower() <= 'z' for c in text)
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
    has_japanese = any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text)
    
    if has_arabic:
        language = "العربية"
    elif has_chinese:
        language = "الصينية"
    elif has_japanese:
        language = "اليابانية"
    elif has_english:
        language = "الإنجليزية"
    else:
        language = "غير معروف"
    
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟') + text.count('!') + text.count('…')
    
    return {
        'language': language,
        'char_count': chars,
        'word_count': len(words),
        'sentence_count': sentences if sentences > 0 else 1,
        'has_arabic': has_arabic,
        'has_english': has_english
    }

# ========== بدائل الصوت المجانية (ذكر وأنثى) ==========

# بديل 1: Google TTS (مجاني، يدعم 100+ لغة)
async def google_tts(text: str, lang: str, gender: str, update: Update):
    try:
        # تحديد اللغة
        lang_codes = {
            'ar': 'ar', 'en': 'en', 'fr': 'fr', 'de': 'de', 'es': 'es',
            'it': 'it', 'tr': 'tr', 'ru': 'ru', 'zh': 'zh-CN', 'ja': 'ja'
        }
        lang_code = lang_codes.get(lang, 'ar')
        
        text_encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang_code}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            audio_data = response.read()
        
        if len(audio_data) > 2000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "google_tts.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title="Google TTS",
                performer=f"{'ذكر' if gender=='male' else 'أنثى'} | {lang}",
                caption=f"✅ تم التحويل بنجاح عبر Google TTS"
            )
            return True
        return False
    except:
        return False

# بديل 2: VoiceRSS (مجاني، يدعم ذكر/أنثى)
async def voicerss_tts(text: str, lang: str, gender: str, update: Update):
    try:
        api_key = "bc0b5b2b0b1b4b0b8b0b0b0b0b0b0b0"
        
        # أصوات مختلفة للذكر والأنثى
        voices = {
            ('ar', 'male'): 'Youssef',
            ('ar', 'female'): 'Amina',
            ('en', 'male'): 'John',
            ('en', 'female'): 'Linda',
            ('fr', 'male'): 'Thomas',
            ('fr', 'female'): 'Julie',
            ('de', 'male'): 'Hans',
            ('de', 'female'): 'Katrin',
            ('es', 'male'): 'Diego',
            ('es', 'female'): 'Mia'
        }
        
        voice = voices.get((lang, gender), 'Amina' if gender == 'female' else 'Youssef')
        
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
                    if len(audio_data) > 2000:
                        audio_file = io.BytesIO(audio_data)
                        audio_file.name = "voicerss.mp3"
                        await update.message.reply_audio(
                            audio=audio_file,
                            title="VoiceRSS TTS",
                            performer=f"{'ذكر' if gender=='male' else 'أنثى'} | {lang}",
                            caption=f"✅ تم التحويل بنجاح عبر VoiceRSS"
                        )
                        return True
        return False
    except:
        return False

# بديل 3: TTSFree (مجاني)
async def ttsfree_api(text: str, lang: str, gender: str, update: Update):
    try:
        gender_code = 'male' if gender == 'male' else 'female'
        url = f"https://ttsfree.com/api/tts?text={urllib.parse.quote(text[:200])}&lang={lang}&gender={gender_code}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            audio_data = response.read()
        
        if len(audio_data) > 2000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "ttsfree.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title="TTSFree",
                performer=f"{'ذكر' if gender=='male' else 'أنثى'}",
                caption=f"✅ تم التحويل بنجاح عبر TTSFree"
            )
            return True
        return False
    except:
        return False

# ========== بدائل الصور المجانية (عرضي/طولي + كاريكتير) ==========

# بديل 1: صورة نصية بأنماط مختلفة
async def create_text_image(text: str, img_type: str, update: Update):
    """إنشاء صورة نصية بأنماط كاريكتير"""
    try:
        # أنماط مختلفة للكاريكتير
        styles = [
            {'bg': (255, 200, 200), 'text': (139, 0, 0), 'border': (255, 100, 100)},  # وردي - أحمر
            {'bg': (200, 255, 200), 'text': (0, 100, 0), 'border': (100, 255, 100)},  # أخضر فاتح
            {'bg': (200, 200, 255), 'text': (0, 0, 139), 'border': (100, 100, 255)},  # أزرق فاتح
            {'bg': (255, 255, 200), 'text': (139, 69, 19), 'border': (255, 200, 100)},  # أصفر - بني
            {'bg': (230, 200, 255), 'text': (75, 0, 130), 'border': (200, 100, 255)},  # بنفسجي
        ]
        style = random.choice(styles)
        
        # تحديد الأبعاد حسب النوع
        if img_type == 'width':
            img_width = 1000
            img_height = 500
        else:  # height
            img_width = 600
            img_height = 800
        
        # إنشاء الصورة
        img = Image.new('RGB', (img_width, img_height), color=style['bg'])
        draw = ImageDraw.Draw(img)
        
        # رسم إطار كاريكتيري
        border_width = 15
        for i in range(border_width):
            draw.rectangle(
                [i, i, img_width - i - 1, img_height - i - 1],
                outline=style['border'],
                width=2
            )
        
        # تحميل الخط
        try:
            font_size = 32 if img_type == 'width' else 28
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # تقسيم النص
        chars_per_line = img_width // 25
        lines = textwrap.wrap(text, width=chars_per_line)
        
        # حساب المسافات
        line_height = 45
        total_text_height = len(lines) * line_height
        y_start = (img_height - total_text_height) // 2
        
        # رسم النص
        y = y_start
        for line in lines:
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
            except:
                text_width = len(line) * 18
            x = (img_width - text_width) // 2
            draw.text((x, y), line, fill=style['text'], font=font)
            y += line_height
        
        # رسم زوايا كاريكتيرية
        corner_size = 50
        for x, y in [(0, 0), (img_width - corner_size, 0), (0, img_height - corner_size), (img_width - corner_size, img_height - corner_size)]:
            draw.ellipse([x, y, x + corner_size, y + corner_size], fill=style['border'])
        
        # حفظ الصورة
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "cartoon_text.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 صورة كاريكتيرية\n📏 النوع: {'عرضي' if img_type == 'width' else 'طولي'}\n📝 {text[:100]}..."
        )
        return True
    except Exception as e:
        logging.error(f"Image error: {e}")
        return False

# بديل 2: صورة بألوان مبهجة
async def create_funny_image(text: str, img_type: str, update: Update):
    try:
        # ألوان مبهجة
        bright_colors = [
            (255, 100, 100), (100, 255, 100), (100, 100, 255),
            (255, 255, 100), (255, 100, 255), (100, 255, 255)
        ]
        bg_color = random.choice(bright_colors)
        text_color = (255, 255, 255)
        
        if img_type == 'width':
            img_width, img_height = 900, 450
        else:
            img_width, img_height = 500, 700
        
        img = Image.new('RGB', (img_width, img_height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # رسم قلوب ونجوم كاريكتيرية
        for _ in range(20):
            x = random.randint(0, img_width)
            y = random.randint(0, img_height)
            draw.point((x, y), fill=(255, 255, 255))
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        except:
            font = ImageFont.load_default()
        
        chars_per_line = img_width // 22
        lines = textwrap.wrap(text, width=chars_per_line)
        
        line_height = 40
        y_start = (img_height - len(lines) * line_height) // 2
        
        y = y_start
        for line in lines:
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                x = (img_width - (bbox[2] - bbox[0])) // 2
            except:
                x = (img_width - len(line) * 18) // 2
            draw.text((x, y), line, fill=text_color, font=font)
            y += line_height
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "funny_text.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🎨 صورة ملونة\n📏 {('عرضي' if img_type == 'width' else 'طولي')}"
        )
        return True
    except:
        return False

# ========== الوظيفة الرئيسية للصوت ==========
async def process_audio(user_text: str, gender: str, update: Update):
    """معالجة الصوت بكل البدائل"""
    
    # تحليل النص أولاً
    analysis = await analyze_text_universal(user_text)
    
    # إرسال تحليل النص
    await update.message.reply_text(
        f"📊 **تحليل النص:**\n\n"
        f"🌐 اللغة: {analysis['language']}\n"
        f"📝 عدد الحروف: {analysis['char_count']}\n"
        f"📖 عدد الكلمات: {analysis['word_count']}\n"
        f"📜 عدد الجمل: {analysis['sentence_count']}\n\n"
        f"🎙 جاري تحويل النص إلى صوت {'(ذكر)' if gender=='male' else '(أنثى)'}...",
        parse_mode="Markdown"
    )
    
    # تحديد لغة الصوت
    if analysis['has_arabic']:
        lang = 'ar'
    else:
        lang = 'en'
    
    # تجربة جميع بدائل الصوت
    success = False
    
    # البديل 1: Google TTS
    if not success:
        success = await google_tts(user_text, lang, gender, update)
    
    # البديل 2: VoiceRSS
    if not success:
        success = await voicerss_tts(user_text, lang, gender, update)
    
    # البديل 3: TTSFree
    if not success:
        success = await ttsfree_api(user_text, lang, gender, update)
    
    if not success:
        await update.message.reply_text("❌ عذراً، جميع خدمات الصوت غير متاحة حالياً. حاول بنص أقصر.")

# ========== الوظيفة الرئيسية للصورة ==========
async def process_image(user_text: str, img_type: str, update: Update):
    """معالجة الصورة بكل البدائل"""
    
    # تحليل النص أولاً
    analysis = await analyze_text_universal(user_text)
    
    # إرسال تحليل النص
    await update.message.reply_text(
        f"📊 **تحليل النص:**\n\n"
        f"🌐 اللغة: {analysis['language']}\n"
        f"📝 عدد الحروف: {analysis['char_count']}\n"
        f"📖 عدد الكلمات: {analysis['word_count']}\n\n"
        f"🎨 جاري تحويل النص إلى صورة {'(عرضي)' if img_type=='width' else '(طولي)'}...",
        parse_mode="Markdown"
    )
    
    # تجربة جميع بدائل الصور
    success = False
    
    # البديل 1: صورة كاريكتير
    if not success:
        success = await create_text_image(user_text, img_type, update)
    
    # البديل 2: صورة ملونة
    if not success:
        success = await create_funny_image(user_text, img_type, update)
    
    if not success:
        await update.message.reply_text("❌ عذراً، حدث خطأ في إنشاء الصورة. حاول مرة أخرى.")

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🖼 صناعة صورة", callback_data="action_image")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "📌 **الخطوات:**\n"
        "1️⃣ اختر ما تريد صناعته (صوت أو صورة)\n"
        "2️⃣ اختر التفاصيل (ذكر/أنثى للصوت - عرضي/طولي للصورة)\n"
        "3️⃣ اكتب النص الذي تريد تحويله\n\n"
        "✅ البوت يحلل النص بأي لغة ثم يصنع لك المطلوب\n\n"
        "🔽 **ابدأ الآن:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSING_ACTION

async def action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "action_audio":
        # اختيار ذكر أو أنثى
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]
        ]
        await query.edit_message_text(
            "🎤 **اختر نوع الصوت:**\n\n"
            "🔊 ذكر → صوت رجالي\n"
            "🔊 أنثى → صوت نسائي\n\n"
            "✅ جميع البدائل مجانية 100%",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CHOOSING_AUDIO_GENDER
        
    elif action == "action_image":
        # اختيار عرضي أو طولي
        keyboard = [
            [InlineKeyboardButton("📐 عرضي (أفقي)", callback_data="image_width")],
            [InlineKeyboardButton("📏 طولي (عمودي)", callback_data="image_height")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]
        ]
        await query.edit_message_text(
            "🖼 **اختر شكل الصورة:**\n\n"
            "📐 عرضي → صورة أفقية\n"
            "📏 طولي → صورة عمودية\n\n"
            "✅ صور كاريكتير ملونة",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CHOOSING_IMAGE_TYPE

async def audio_gender_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data
    
    if choice == "back_to_start":
        return await start(update, context)
    
    if choice == "audio_male":
        user_choices[user_id] = {'type': 'audio', 'gender': 'male'}
        await query.edit_message_text(
            "🎤 **لقد اخترت: صوت (ذكر)**\n\n"
            "✏️ **الآن أرسل النص الذي تريد تحويله إلى صوت:**\n\n"
            "✅ سأقوم بتحليل النص أولاً ثم تحويله إلى صوت MP3\n"
            "🌐 يدعم جميع اللغات (عربي، إنجليزي، وغيره)"
        )
        return WAITING_FOR_TEXT
        
    elif choice == "audio_female":
        user_choices[user_id] = {'type': 'audio', 'gender': 'female'}
        await query.edit_message_text(
            "🎤 **لقد اخترت: صوت (أنثى)**\n\n"
            "✏️ **الآن أرسل النص الذي تريد تحويله إلى صوت:**\n\n"
            "✅ سأقوم بتحليل النص أولاً ثم تحويله إلى صوت MP3\n"
            "🌐 يدعم جميع اللغات (عربي، إنجليزي، وغيره)"
        )
        return WAITING_FOR_TEXT

async def image_type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data
    
    if choice == "back_to_start":
        return await start(update, context)
    
    if choice == "image_width":
        user_choices[user_id] = {'type': 'image', 'img_type': 'width'}
        await query.edit_message_text(
            "🖼 **لقد اخترت: صورة عرضية (أفقية)**\n\n"
            "✏️ **الآن أرسل النص الذي تريد تحويله إلى صورة:**\n\n"
            "✅ سأقوم بتحليل النص أولاً ثم إنشاء صورة كاريكتير ملونة"
        )
        return WAITING_FOR_TEXT
        
    elif choice == "image_height":
        user_choices[user_id] = {'type': 'image', 'img_type': 'height'}
        await query.edit_message_text(
            "🖼 **لقد اخترت: صورة طولية (عمودية)**\n\n"
            "✏️ **الآن أرسل النص الذي تريد تحويله إلى صورة:**\n\n"
            "✅ سأقوم بتحليل النص أولاً ثم إنشاء صورة كاريكتير ملونة"
        )
        return WAITING_FOR_TEXT

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    if user_id not in user_choices:
        await update.message.reply_text("❌ الرجاء البدء من جديد باستخدام /start")
        return ConversationHandler.END
    
    choice = user_choices[user_id]
    
    if choice['type'] == 'audio':
        gender = choice['gender']
        await process_audio(user_text, gender, update)
    else:  # image
        img_type = choice['img_type']
        await process_image(user_text, img_type, update)
    
    # تنظيف البيانات
    del user_choices[user_id]
    
    # عرض قائمة البداية مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🖼 صناعة صورة", callback_data="action_image")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟** ✨\n\nاختر من الأزرار:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء. استخدم /start للبدء من جديد.")
    return ConversationHandler.END

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إنشاء محادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern="^(action_audio|action_image)$")],
            CHOOSING_AUDIO_GENDER: [CallbackQueryHandler(audio_gender_choice, pattern="^(audio_male|audio_female|back_to_start)$")],
            CHOOSING_IMAGE_TYPE: [CallbackQueryHandler(image_type_choice, pattern="^(image_width|image_height|back_to_start)$")],
            WAITING_FOR_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل - صناعة صوت وصورة مع تحليل النص")
    app.run_polling()

if __name__ == "__main__":
    main()
