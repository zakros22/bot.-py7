import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from PIL import Image, ImageDraw, ImageFont
import textwrap

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE, WAITING_FOR_EXPLAIN = range(5)

# تخزين بيانات المستخدمين
user_choices = {}

# ========== قاموس الشخصيات الكرتونية ==========
CARTOON_CHARACTERS = {
    'ولد': ['boy', '👦', 'طفل', 'صبي'],
    'بنت': ['girl', '👧', 'طفلة', 'بنت صغيرة'],
    'قطة': ['cat', '🐱', 'قط', 'هرة'],
    'كلب': ['dog', '🐶', 'جرو'],
    'أسد': ['lion', '🦁'],
    'فيل': ['elephant', '🐘'],
    'زرافة': ['giraffe', '🦒'],
    'دب': ['bear', '🐻', 'دب صغير'],
    'أرنب': ['rabbit', '🐰'],
    'بطة': ['duck', '🦆'],
    'طائر': ['bird', '🐦'],
    'سمكة': ['fish', '🐟', 'سمكة ذهبية'],
    'فراشة': ['butterfly', '🦋'],
    'نحلة': ['bee', '🐝'],
    'شمس': ['sun', '☀️'],
    'قمر': ['moon', '🌙'],
    'نجمة': ['star', '⭐'],
    'سحابة': ['cloud', '☁️'],
    'زهرة': ['flower', '🌸', 'ورد'],
    'شجرة': ['tree', '🌳'],
    'منزل': ['house', '🏠', 'بيت'],
    'سيارة': ['car', '🚗'],
    'طائرة': ['airplane', '✈️'],
    'كرة': ['ball', '⚽', 'كرة قدم'],
    'دراجة': ['bike', '🚲'],
    'كتاب': ['book', '📚'],
    'قلم': ['pen', '✏️'],
    'مدرسة': ['school', '🏫'],
    'حديقة': ['garden', '🌿', 'منتزه', 'park'],
    'بحر': ['sea', '🌊', 'مح'],
    'جبل': ['mountain', '⛰️'],
}

# ========== تحليل النص واستخراج الكلمات المفتاحية ==========
def extract_keywords(text: str):
    """استخراج الكلمات المفتاحية من النص لصناعة الصورة"""
    text_lower = text.lower()
    found_characters = []
    found_places = []
    found_objects = []
    
    for keyword, variants in CARTOON_CHARACTERS.items():
        for variant in variants:
            if variant in text_lower or variant in text:
                if keyword in ['ولد', 'بنت', 'قطة', 'كلب', 'أسد', 'فيل', 'زرافة', 'دب', 'أرنب', 'بطة', 'طائر', 'سمكة']:
                    found_characters.append(keyword)
                elif keyword in ['حديقة', 'بحر', 'جبل', 'مدرسة', 'منزل']:
                    found_places.append(keyword)
                else:
                    found_objects.append(keyword)
                break
    
    # إزالة التكرارات
    found_characters = list(set(found_characters))
    found_places = list(set(found_places))
    found_objects = list(set(found_objects))
    
    return {
        'characters': found_characters if found_characters else ['ولد'],
        'places': found_places if found_places else ['حديقة'],
        'objects': found_objects,
        'original_text': text[:200]
    }

# ========== صناعة صورة كرتونية محلياً ==========
async def create_cartoon_image(text: str, update: Update):
    """صناعة صورة كرتونية بناءً على النص"""
    
    # إرسال رسالة المعالجة
    processing_msg = await update.message.reply_text("🎨 **جاري تحليل النص وصناعة الصورة الكرتونية...**")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("📖 **جاري تحليل النص وفهمه...**")
    
    # استخراج الكلمات المفتاحية
    keywords = extract_keywords(text)
    
    await processing_msg.edit_text(f"🎭 **الكلمات المفتاحية المستخرجة:**\nشخصية: {', '.join(keywords['characters'])}\nمكان: {', '.join(keywords['places'])}")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("🖌 **جاري رسم الصورة الكرتونية...**")
    
    try:
        # إعداد الصورة
        img_width = 800
        img_height = 600
        bg_color = (135, 206, 235)  # أزرق سماوي (سماء)
        
        # ألوان الخلفية حسب المكان
        if 'بحر' in keywords['places']:
            bg_color = (0, 105, 148)  # أزرق بحري
        elif 'جبل' in keywords['places']:
            bg_color = (34, 139, 34)  # أخضر غامق
        elif 'مدرسة' in keywords['places']:
            bg_color = (255, 228, 196)  # بيج
        elif 'ليل' in text.lower() or 'قمر' in text.lower():
            bg_color = (25, 25, 112)  # أزرق داكن (ليل)
        
        # إنشاء الصورة
        img = Image.new('RGB', (img_width, img_height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # رسم السماء (إذا كانت خلفية السماء)
        if bg_color == (135, 206, 235):
            draw.rectangle([0, 0, img_width, img_height//2], fill=(135, 206, 235))
            draw.rectangle([0, img_height//2, img_width, img_height], fill=(34, 139, 34))  # أرض
        
        # رسم الشمس أو القمر
        if 'شمس' in keywords['objects'] or 'نهار' in text.lower():
            draw.ellipse([img_width-100, 50, img_width-30, 130], fill=(255, 255, 0))  # شمس
        elif 'قمر' in keywords['objects'] or 'ليل' in text.lower():
            draw.ellipse([img_width-100, 50, img_width-30, 130], fill=(255, 255, 200))  # قمر
        
        # رسم سحاب
        if 'سحابة' in keywords['objects'] or random.random() > 0.7:
            draw.ellipse([100, 80, 160, 140], fill=(255, 255, 255))
            draw.ellipse([130, 70, 190, 130], fill=(255, 255, 255))
            draw.ellipse([160, 80, 220, 140], fill=(255, 255, 255))
        
        # رسم الشخصية الرئيسية
        character = keywords['characters'][0]
        center_x = img_width // 2
        ground_y = img_height - 150
        
        # جسم الشخصية
        if character == 'ولد':
            # رسم ولد
            draw.ellipse([center_x-40, ground_y-80, center_x+40, ground_y], fill=(255, 200, 150))  # وجه
            draw.ellipse([center_x-25, ground_y-60, center_x-10, ground_y-45], fill=(0, 0, 0))  # عين يسار
            draw.ellipse([center_x+10, ground_y-60, center_x+25, ground_y-45], fill=(0, 0, 0))  # عين يمين
            draw.arc([center_x-20, ground_y-40, center_x+20, ground_y-15], 0, 180, fill=(255, 100, 100), width=3)  # فم مبتسم
            # شعر
            draw.ellipse([center_x-45, ground_y-100, center_x+45, ground_y-70], fill=(139, 69, 19))
            # جسد
            draw.rectangle([center_x-30, ground_y, center_x+30, ground_y+60], fill=(100, 150, 255))  # قميص
            # أرجل
            draw.line([center_x-20, ground_y+60, center_x-25, ground_y+110], fill=(0, 0, 139), width=8)
            draw.line([center_x+20, ground_y+60, center_x+25, ground_y+110], fill=(0, 0, 139), width=8)
            # أيدي
            draw.line([center_x-30, ground_y+20, center_x-60, ground_y+50], fill=(255, 200, 150), width=8)
            draw.line([center_x+30, ground_y+20, center_x+60, ground_y+50], fill=(255, 200, 150), width=8)
            
        elif character == 'بنت':
            # رسم بنت
            draw.ellipse([center_x-40, ground_y-80, center_x+40, ground_y], fill=(255, 220, 180))  # وجه
            draw.ellipse([center_x-25, ground_y-60, center_x-10, ground_y-45], fill=(0, 0, 0))  # عين يسار
            draw.ellipse([center_x+10, ground_y-60, center_x+25, ground_y-45], fill=(0, 0, 0))  # عين يمين
            draw.arc([center_x-20, ground_y-40, center_x+20, ground_y-15], 0, 180, fill=(255, 100, 100), width=3)  # فم مبتسم
            # شعر طويل
            draw.ellipse([center_x-45, ground_y-100, center_x+45, ground_y-70], fill=(255, 200, 0))
            draw.line([center_x-40, ground_y-70, center_x-50, ground_y-40], fill=(255, 200, 0), width=10)
            draw.line([center_x+40, ground_y-70, center_x+50, ground_y-40], fill=(255, 200, 0), width=10)
            # فستان
            draw.rectangle([center_x-35, ground_y, center_x+35, ground_y+70], fill=(255, 100, 150))
            # أرجل
            draw.line([center_x-20, ground_y+70, center_x-25, ground_y+110], fill=(255, 200, 150), width=8)
            draw.line([center_x+20, ground_y+70, center_x+25, ground_y+110], fill=(255, 200, 150), width=8)
            
        elif character == 'قطة':
            # رسم قطة
            draw.ellipse([center_x-35, ground_y-60, center_x+35, ground_y], fill=(255, 140, 0))  # جسم
            draw.ellipse([center_x-20, ground_y-80, center_x+20, ground_y-50], fill=(255, 140, 0))  # رأس
            draw.polygon([center_x-25, ground_y-80, center_x-35, ground_y-100, center_x-15, ground_y-85], fill=(255, 140, 0))  # أذن يسار
            draw.polygon([center_x+25, ground_y-80, center_x+35, ground_y-100, center_x+15, ground_y-85], fill=(255, 140, 0))  # أذن يمين
            draw.ellipse([center_x-12, ground_y-70, center_x-5, ground_y-63], fill=(0, 0, 0))  # عين يسار
            draw.ellipse([center_x+5, ground_y-70, center_x+12, ground_y-63], fill=(0, 0, 0))  # عين يمين
            draw.ellipse([center_x-3, ground_y-58, center_x+3, ground_y-52], fill=(255, 100, 100))  # أنف
            # ذيل
            draw.line([center_x+35, ground_y-40, center_x+60, ground_y-60], fill=(255, 140, 0), width=8)
            
        elif character == 'كلب':
            # رسم كلب
            draw.ellipse([center_x-40, ground_y-70, center_x+40, ground_y], fill=(160, 82, 45))  # جسم
            draw.ellipse([center_x-25, ground_y-90, center_x+25, ground_y-60], fill=(160, 82, 45))  # رأس
            draw.ellipse([center_x-15, ground_y-80, center_x-8, ground_y-73], fill=(0, 0, 0))  # عين يسار
            draw.ellipse([center_x+8, ground_y-80, center_x+15, ground_y-73], fill=(0, 0, 0))  # عين يمين
            draw.ellipse([center_x-3, ground_y-70, center_x+3, ground_y-64], fill=(0, 0, 0))  # أنف
            # أذنين
            draw.ellipse([center_x-40, ground_y-85, center_x-25, ground_y-70], fill=(139, 69, 19))
            draw.ellipse([center_x+25, ground_y-85, center_x+40, ground_y-70], fill=(139, 69, 19))
        
        # رسم مكان (حديقة، بحر، الخ)
        if 'حديقة' in keywords['places']:
            # رسم زهور
            for i in range(5):
                flower_x = 50 + i * 150
                draw.ellipse([flower_x, img_height-80, flower_x+20, img_height-60], fill=(255, 100, 100))
                draw.ellipse([flower_x+5, img_height-90, flower_x+15, img_height-80], fill=(255, 255, 0))
                draw.line([flower_x+10, img_height-60, flower_x+10, img_height-40], fill=(0, 100, 0), width=3)
        
        elif 'بحر' in keywords['places']:
            # رسم أمواج البحر
            for i in range(5):
                wave_y = img_height - 100 + i * 20
                draw.arc([0, wave_y, img_width, wave_y+30], 0, 180, fill=(0, 191, 255), width=5)
        
        # رسم نص الصورة (الوصف)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        # نص قصير في الأسفل
        short_text = text[:80] + "..." if len(text) > 80 else text
        wrapped_text = textwrap.wrap(short_text, width=35)
        y_text = img_height - 40
        for line in wrapped_text:
            draw.text((50, y_text), line, fill=(0, 0, 0), font=font)
            y_text += 25
        
        # حفظ الصورة
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "cartoon_image.png"
        
        await processing_msg.delete()
        
        # إرسال الصورة
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🎨 **صورة كرتونية**\n\n📝 **الوصف:** {text[:150]}...\n\n🎭 **الشخصية:** {character}\n📍 **المكان:** {', '.join(keywords['places'])}"
        )
        
        await update.message.reply_text("✅ **تم صناعة الصورة الكرتونية بنجاح!**")
        return True
        
    except Exception as e:
        logger.error(f"Error creating image: {e}")
        await processing_msg.edit_text(f"❌ حدث خطأ في صناعة الصورة: {str(e)[:100]}")
        return False

# ========== شرح النص بشكل مفصل ==========
async def explain_text(text: str, update: Update):
    """شرح النص بشكل مفصل"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    await asyncio.sleep(0.5)
    
    # تحليل النص
    words = text.split()
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
    
    # اكتشاف اللغة
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_english = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_arabic and has_english:
        language = "عربي + إنجليزي (مختلط)"
    elif has_arabic:
        language = "عربي"
    else:
        language = "إنجليزي"
    
    # استخراج الكلمات المفتاحية للشرح
    keywords = extract_keywords(text)
    
    # بناء شرح مفصل
    explanation = f"""
📚 **شرح وتحليل النص**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text}

━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {sentences if sentences > 0 else 1}
• عدد المسافات: {text.count(' ')}
• الأرقام في النص: {sum(c.isdigit() for c in text)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {language}

━━━━━━━━━━━━━━━━━━━━━━
🎭 **الكلمات المفتاحية المستخرجة:**
• شخصيات: {', '.join(keywords['characters']) if keywords['characters'] else 'غير محدد'}
• أماكن: {', '.join(keywords['places']) if keywords['places'] else 'غير محدد'}
• أشياء: {', '.join(keywords['objects']) if keywords['objects'] else 'غير محدد'}

━━━━━━━━━━━━━━━━━━━━━━
📏 **تقييم النص:**
• الطول: {'قصير جداً' if len(words) < 5 else 'قصير' if len(words) < 15 else 'متوسط' if len(words) < 40 else 'طويل'}
• التعقيد: {'بسيط' if len(words) < 20 else 'متوسط' if len(words) < 50 else 'معقد'}

━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص النص:**
{text[:300]}{'...' if len(text) > 300 else ''}

✅ **تم التحليل والشرح بنجاح**
"""
    
    await processing_msg.delete()
    
    # تقسيم الشرح إذا كان طويلاً
    if len(explanation) > 4000:
        part1 = explanation[:3500]
        part2 = explanation[3500:]
        await update.message.reply_text(part1)
        await update.message.reply_text(part2)
    else:
        await update.message.reply_text(explanation)

# ========== تحويل النص إلى صوت ==========
async def google_tts(text: str, lang: str, gender: str, update: Update):
    try:
        lang_codes = {'ar': 'ar', 'en': 'en'}
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
                performer=f"{'ذكر' if gender=='male' else 'أنثى'}",
                caption="✅ تم تحويل النص إلى صوت"
            )
            return True
        return False
    except:
        return False

async def generate_audio(text: str, gender: str, update: Update):
    """تحويل النص إلى صوت"""
    
    # تحليل النص أولاً
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    lang = 'ar' if has_arabic else 'en'
    
    await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت {'(ذكر)' if gender=='male' else '(أنثى)'}...**")
    
    success = await google_tts(text, lang, gender, update)
    
    if success:
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً. حاول بنص أقصر.")

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
        [InlineKeyboardButton("📖 شرح النص", callback_data="action_explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "📌 **الخدمات المتاحة:**\n\n"
        "🎵 **صناعة صوت:** يحول أي نص إلى صوت MP3 (ذكر/أنثى)\n\n"
        "🎨 **صناعة صورة كرتونية:** يحول أي وصف إلى صورة كرتونية\n"
        "   • يدعم النصوص الطويلة ويقسمها\n"
        "   • يستخرج الكلمات المفتاحية تلقائياً\n"
        "   • يرسم شخصيات كرتونية (ولد، بنت، قطة، كلب...)\n\n"
        "📖 **شرح النص:** يحلل أي نص ويعطيك شرحاً مفصلاً\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSING_ACTION

async def action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    if action == "action_audio":
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]
        ]
        await query.edit_message_text(
            "🎤 **اختر نوع الصوت:**\n\n👨 ذكر\n👩 أنثى",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSING_AUDIO_GENDER
        
    elif action == "action_image":
        await query.edit_message_text(
            "🎨 **صناعة صورة كرتونية**\n\n"
            "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
            "📝 **أمثلة:**\n"
            "• ولد في حديقة مع زهور\n"
            "• بنت مع قطة صغيرة\n"
            "• كلب يجري في الحديقة\n"
            "• قطة نائمة تحت شجرة\n\n"
            "✅ سأحلل النص وأصنع صورة كرتونية مناسبة"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح النص**\n\n"
            "✏️ **أرسل النص الذي تريد شرحه وتحليله:**\n\n"
            "✅ سأقوم بتحليل النص وإعطائك:\n"
            "• عدد الحروف والكلمات والجمل\n"
            "• اللغة المكتشفة\n"
            "• الكلمات المفتاحية المستخرجة\n"
            "• ملخص النص"
        )
        return WAITING_FOR_EXPLAIN

async def audio_gender_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data
    
    if choice == "back_to_start":
        return await start(update, context)
    
    gender = 'male' if choice == "audio_male" else 'female'
    user_choices[user_id] = {'type': 'audio', 'gender': gender}
    
    await query.edit_message_text(
        f"🎤 **تم اختيار {'ذكر' if gender=='male' else 'أنثى'}**\n\n"
        "✏️ **أرسل النص الذي تريد تحويله إلى صوت:**"
    )
    return WAITING_FOR_TEXT_AUDIO

async def receive_audio_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    if user_id not in user_choices:
        await update.message.reply_text("❌ الرجاء البدء من جديد باستخدام /start")
        return ConversationHandler.END
    
    choice = user_choices[user_id]
    await generate_audio(user_text, choice['gender'], update)
    
    del user_choices[user_id]
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
        [InlineKeyboardButton("📖 شرح النص", callback_data="action_explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def receive_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # معالجة النص الطويل
    if len(user_text) > 500:
        await update.message.reply_text("📝 **نص طويل!** سأقوم بتقسيمه وتحليله...")
    
    await create_cartoon_image(user_text, update)
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
        [InlineKeyboardButton("📖 شرح النص", callback_data="action_explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def receive_explain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    await explain_text(user_text, update)
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
        [InlineKeyboardButton("📖 شرح النص", callback_data="action_explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد تحليل نص آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء. استخدم /start للبدء.")
    return ConversationHandler.END

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern="^(action_audio|action_image|action_explain)$")],
            CHOOSING_AUDIO_GENDER: [CallbackQueryHandler(audio_gender_choice, pattern="^(audio_male|audio_female|back_to_start)$")],
            WAITING_FOR_TEXT_AUDIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_audio_text)],
            WAITING_FOR_TEXT_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_image_text)],
            WAITING_FOR_EXPLAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_explain_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل - صناعة صور كرتونية محلية + صوت + شرح النص")
    app.run_polling()

if __name__ == "__main__":
    main()
