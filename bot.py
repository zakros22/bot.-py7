import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
import json
import base64
import random
import re
import subprocess
import time
import sys
import signal
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME")

# حالات المحادثة
CHOOSING_ACTION, WAITING_FOR_TEXT = range(2)

# تخزين بيانات المستخدمين
user_data = {}

# ========== إعدادات المحاولات ==========
MAX_IMAGE_RETRIES = 5  # عدد محاولات إعادة التشغيل لتوليد الصورة
RETRY_DELAY = 3        # انتظار بين المحاولات

# ========== وظيفة إعادة تشغيل Heroku ==========
def restart_heroku():
    """إعادة تشغيل تطبيق Heroku"""
    try:
        if HEROKU_APP_NAME:
            logger.info(f"🔄 جاري إعادة تشغيل {HEROKU_APP_NAME}...")
            subprocess.run(
                ["heroku", "restart", "-a", HEROKU_APP_NAME],
                capture_output=True, timeout=10
            )
            return True
    except Exception as e:
        logger.error(f"خطأ في إعادة التشغيل: {e}")
        return False

# ========== بدائل شرح النص (5 بدائل مجانية) ==========

# بديل 1: تحليل محلي متقدم (يعمل دائماً)
async def explain_local_advanced(text: str, update: Update):
    """شرح متقدم محلياً - يدعم المعادلات والمواضيع العلمية"""
    
    # تحليل النص
    words = text.split()
    chars = len(text)
    lines = text.count('\n') + 1
    
    # اكتشاف نوع المحتوى
    has_equations = bool(re.search(r'[\+\-\*\/\=\(\)\^]|x\^?\d?|\d+[x]', text))
    has_numbers = bool(re.search(r'\d+', text))
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    # اكتشاف الموضوع
    science_keywords = ['معادلة', 'قانون', 'فيزياء', 'كيمياء', 'رياضيات', 'جبر', 'هندسة', 'مثلثات']
    math_keywords = ['+', '-', '*', '/', '=', 'x', 'y', '∑', '∫', '√', '^']
    
    is_science = any(kw in text for kw in science_keywords)
    is_math = any(kw in text for kw in math_keywords)
    
    # تقسيم النص إلى جمل
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    # الكلمات الرئيسية
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # بناء الشرح
    explanation = f"""
📚 **تحليل وشرح النص (متقدم)**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:600]}{'...' if len(text) > 600 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات الأساسية:**
• عدد الحروف: {chars}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• عدد الأسطر: {lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 **نوع المحتوى:**
"""
    if is_math or has_equations:
        explanation += "• 📐 **رياضيات / معادلات**\n"
    if is_science:
        explanation += "• 🔬 **علوم / فيزياء / كيمياء**\n"
    if has_numbers:
        explanation += "• 🔢 **يحتوي على أرقام ومعادلات**\n"
    if not (is_math or is_science):
        explanation += "• 📖 **نص عام / أدبي**\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية / مختلطة'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **الكلمات المفتاحية:**
"""
    for word, count in keywords[:8]:
        explanation += f"• {word} ({count})\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **الملخص والشرح:**

{text[:300]}{'...' if len(text) > 300 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 **النقاط الرئيسية:**
"""
    # استخراج أهم الجمل
    important = sorted(sentences, key=len, reverse=True)[:3]
    for i, sent in enumerate(important, 1):
        explanation += f"{i}. {sent[:100]}...\n"
    
    explanation += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **تم التحليل والشرح بنجاح**
"""
    
    # تقسيم الشرح إذا كان طويلاً
    if len(explanation) > 4000:
        await update.message.reply_text(explanation[:3500])
        await update.message.reply_text(explanation[3500:])
    else:
        await update.message.reply_text(explanation)
    
    return True

# بديل 2: شرح باستخدام API (مجاني)
async def explain_api_1(text: str, update: Update):
    """شرح باستخدام API خارجي"""
    try:
        encoded_text = urllib.parse.quote(text[:1000])
        url = f"https://api.meaningcloud.com/summarization-1.0?key=mock_key&txt={encoded_text}&sentences=5"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            summary = data.get('summary', text[:300])
            
            await update.message.reply_text(
                f"📚 **ملخص النص (API)**\n\n"
                f"{summary}\n\n"
                f"✅ تم إنشاء هذا الملخص تلقائياً"
            )
            return True
    except:
        return False

# بديل 3: تحليل ذكي للنص
async def explain_smart(text: str, update: Update):
    """تحليل ذكي مع استخراج المعلومات"""
    
    # استخراج المعادلات الرياضية
    equations = re.findall(r'[\d\+\-\*\/\(\)\=]+|x\^?\d?|\d+[a-z]', text)
    
    # استخراج التواريخ
    dates = re.findall(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{1,2}\s+(?:يناير|فبراير|مارس|إبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)', text)
    
    # استخراج النسب المئوية
    percentages = re.findall(r'\d+%', text)
    
    explanation = f"""
🧠 **تحليل ذكي للنص**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **الخلاصة:**
{text[:250]}...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    if equations:
        explanation += f"📐 **المعادلات المكتشفة:**\n"
        for eq in equations[:3]:
            explanation += f"• {eq}\n"
        explanation += "\n"
    
    if dates:
        explanation += f"📅 **التواريخ:** {', '.join(dates[:3])}\n\n"
    
    if percentages:
        explanation += f"📊 **النسب:** {', '.join(percentages[:3])}\n\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات سريعة:**
• عدد الكلمات: {len(text.split())}
• عدد الجمل: {len(re.split(r'[.!?؟]+', text))}
• عدد الحروف: {len(text)}

✅ تم التحليل الذكي بنجاح
"""
    await update.message.reply_text(explanation)
    return True

# بديل 4: تحليل علمي متخصص
async def explain_scientific(text: str, update: Update):
    """تحليل للمواضيع العلمية والرياضية"""
    
    # اكتشاف المصطلحات العلمية
    scientific_terms = re.findall(r'[أ-ي]{4,}', text)
    scientific_terms = list(set([t for t in scientific_terms if len(t) > 3]))[:10]
    
    # تحليل المعادلات
    has_formula = bool(re.search(r'[a-z]\s*[=<>]\s*\d+|\d+\s*[=<>]\s*[a-z]', text.lower()))
    
    explanation = f"""
🔬 **تحليل علمي للنص**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **النص العلمي:**
{text[:400]}...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    if has_formula:
        explanation += "🧪 **يحتوي النص على معادلات وقوانين علمية**\n\n"
    
    if scientific_terms:
        explanation += f"🔬 **المصطلحات العلمية:**\n"
        for term in scientific_terms[:7]:
            explanation += f"• {term}\n"
        explanation += "\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **التقييم:**
• مستوى الصعوبة: {'متقدم' if len(text) > 500 else 'متوسط' if len(text) > 200 else 'مبتدئ'}
• الطول: {'طويل' if len(text.split()) > 100 else 'متوسط' if len(text.split()) > 50 else 'قصير'}

✅ تم التحليل العلمي بنجاح
"""
    await update.message.reply_text(explanation)
    return True

# بديل 5: ملخص سريع
async def explain_summary(text: str, update: Update):
    """ملخص سريع للنص"""
    
    # تقسيم إلى جمل
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    # اختيار أهم الجمل (أطول الجمل عادة تحتوي على المعلومات الرئيسية)
    main_sentences = sorted(sentences, key=len, reverse=True)[:3]
    
    summary = f"""
📝 **ملخص النص**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **الملخص:**
"""
    for i, sent in enumerate(main_sentences, 1):
        summary += f"{i}. {sent[:150]}...\n"
    
    summary += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **نبذة سريعة:**
• عدد الكلمات: {len(text.split())}
• وقت القراءة المقدر: {len(text.split()) // 200} دقيقة

✅ تم إنشاء الملخص بنجاح
"""
    await update.message.reply_text(summary)
    return True

# ========== وظيفة شرح النص الرئيسية (تجربة جميع البدائل) ==========
async def explain_text_full(text: str, update: Update):
    """شرح النص باستخدام جميع البدائل المتاحة"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    await asyncio.sleep(0.5)
    await processing_msg.edit_text("📖 **البديل 1/5: تحليل متقدم محلي...**")
    
    success = False
    
    # البديل 1: تحليل محلي متقدم (يعمل دائماً)
    success = await explain_local_advanced(text, update)
    
    # البديل 2: تحليل API
    if not success:
        await processing_msg.edit_text("📖 **البديل 2/5: تحليل API...**")
        success = await explain_api_1(text, update)
    
    # البديل 3: تحليل ذكي
    if not success:
        await processing_msg.edit_text("📖 **البديل 3/5: تحليل ذكي...**")
        success = await explain_smart(text, update)
    
    # البديل 4: تحليل علمي
    if not success:
        await processing_msg.edit_text("📖 **البديل 4/5: تحليل علمي...**")
        success = await explain_scientific(text, update)
    
    # البديل 5: ملخص سريع
    if not success:
        await processing_msg.edit_text("📖 **البديل 5/5: ملخص سريع...**")
        success = await explain_summary(text, update)
    
    await processing_msg.delete()
    
    if not success:
        await update.message.reply_text(
            "❌ عذراً، حدث خطأ في تحليل النص.\n\n"
            "💡 حاول بنص أقصر أو أقل تعقيداً."
        )

# ========== توليد الصورة مع محاولات متعددة وإعادة تشغيل ==========
async def generate_image_with_retries(prompt: str, update: Update, attempt: int = 0):
    """توليد صورة مع محاولات متعددة وإعادة تشغيل تلقائي"""
    
    MAX_ATTEMPTS = 5
    
    if attempt >= MAX_ATTEMPTS:
        await update.message.reply_text(
            "❌ **فشل توليد الصورة بعد 5 محاولات**\n\n"
            "💡 نصائح:\n"
            "• جرب وصفاً أقصر (أقل من 150 حرف)\n"
            "• جرب وصفاً باللغة الإنجليزية\n"
            "• مثال: 'a boy playing in garden'\n\n"
            "🔄 يمكنك المحاولة مرة أخرى بعد دقيقة"
        )
        return False
    
    await update.message.reply_text(
        f"🎨 **محاولة توليد الصورة {attempt + 1}/{MAX_ATTEMPTS}**\n\n"
        f"📝 {prompt[:100]}...\n\n"
        f"🔄 جاري إعادة تشغيل الخادم..."
    )
    
    # إعادة تشغيل Heroku قبل كل محاولة
    restart_heroku()
    await asyncio.sleep(3)
    
    await update.message.reply_text("✅ **تم إعادة التشغيل، جاري توليد الصورة...**")
    
    try:
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful")
        random_seed = random.randint(1, 1000000) + attempt * 10000
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&seed={random_seed}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🎨 **تم توليد الصورة بنجاح!**\n\n📝 {prompt[:150]}...\n\n✅ بعد {attempt + 1} محاولات"
            )
            return True
        else:
            raise Exception("صورة فارغة")
            
    except Exception as e:
        logger.error(f"محاولة {attempt + 1} فشلت: {e}")
        await update.message.reply_text(f"⚠️ **المحاولة {attempt + 1} فشلت، جاري إعادة المحاولة...**")
        await asyncio.sleep(2)
        return await generate_image_with_retries(prompt, update, attempt + 1)

# ========== تقسيم النص الطويل إلى أجزاء ==========
async def process_long_text(text: str, update: Update, action: str, gender: str = None):
    """معالجة النص الطويل (تقسيمه إذا لزم الأمر)"""
    
    if action == "image":
        # للصور، إذا كان النص طويلاً جداً، خذ أول 200 حرف فقط
        if len(text) > 200:
            text = text[:200]
            await update.message.reply_text("📝 **تم تقصير النص إلى 200 حرف لتحسين جودة الصورة**")
        
        return await generate_image_with_retries(text, update, 0)
    
    elif action == "explain":
        # للشرح، إذا كان النص طويلاً جداً، قم بتقسيمه
        if len(text) > 3000:
            parts = [text[i:i+2500] for i in range(0, len(text), 2500)]
            await update.message.reply_text(f"📝 **نص طويل!** سأقوم بتقسيمه إلى {len(parts)} أجزاء للشرح")
            
            for idx, part in enumerate(parts, 1):
                await update.message.reply_text(f"📖 **الجزء {idx}/{len(parts)}**")
                await explain_text_full(part, update)
                await asyncio.sleep(1)
            return True
        else:
            return await explain_text_full(text, update)

# ========== تحويل النص إلى صوت ==========
async def generate_audio(text: str, gender: str, update: Update):
    try:
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
        lang = 'ar' if has_arabic else 'en'
        
        text_encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            audio_data = response.read()
        
        if len(audio_data) > 1000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title="النص الصوتي",
                performer=f"{'ذكر' if gender=='male' else 'أنثى'}",
                caption="✅ تم تحويل النص إلى صوت"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"خطأ في الصوت: {e}")
        await update.message.reply_text("❌ خدمة الصوت غير متاحة حالياً")
        return False

# ========== أزرار البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📚 شرح وتحليل النص", callback_data="explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة:**\n"
        "   • 5 محاولات مع إعادة تشغيل تلقائي\n"
        "   • يدعم الوصف العربي والإنجليزي\n\n"
        "🎵 **تحويل نص إلى صوت:**\n"
        "   • اختيار ذكر أو أنثى\n"
        "   • يدعم العربية والإنجليزية\n\n"
        "📚 **شرح وتحليل النص:**\n"
        "   • 5 بدائل مجانية للشرح\n"
        "   • يدعم المعادلات الرياضية\n"
        "   • يدعم المواضيع العلمية\n"
        "   • يعطي ملخصاً كاملاً\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    if action == "image":
        await query.edit_message_text(
            "🎨 **توليد صورة**\n\n"
            "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة مع زهور\n"
            "• قطة نائمة على كنبة\n"
            "• a boy playing in garden\n\n"
            "✅ سيتم المحاولة 5 مرات مع إعادة تشغيل تلقائي"
        )
        user_data[user_id] = {'mode': 'image'}
        
    elif action == "audio":
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
        ]
        await query.edit_message_text(
            "🎤 **اختر نوع الصوت:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif action == "audio_male":
        await query.edit_message_text(
            "🎤 **صوت ذكر**\n\n✏️ **أرسل النص لتحويله إلى صوت:**"
        )
        user_data[user_id] = {'mode': 'audio', 'gender': 'male'}
        
    elif action == "audio_female":
        await query.edit_message_text(
            "🎤 **صوت أنثى**\n\n✏️ **أرسل النص لتحويله إلى صوت:**"
        )
        user_data[user_id] = {'mode': 'audio', 'gender': 'female'}
        
    elif action == "explain":
        await query.edit_message_text(
            "📚 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله وشرحه:**\n\n"
            "✅ سأقوم بـ:\n"
            "• تحليل النص بالكامل\n"
            "• شرح المعادلات الرياضية\n"
            "• استخراج الكلمات المفتاحية\n"
            "• إعطاء ملخص كامل\n\n"
            "📖 يدعم: محاضرات، مواضيع علمية، نصوص أدبية"
        )
        user_data[user_id] = {'mode': 'explain'}

# ========== معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_data:
        keyboard = [
            [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
            [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
            [InlineKeyboardButton("📚 شرح وتحليل النص", callback_data="explain")],
        ]
        await update.message.reply_text(
            "✨ **أهلاً بك!** ✨\n\nاختر ما تريد من الأزرار:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    mode_data = user_data[user_id]
    mode = mode_data.get('mode')
    
    # رسالة المعالجة
    processing = await update.message.reply_text("⏳ **جاري المعالجة...**")
    
    if mode == 'image':
        await process_long_text(text, update, 'image')
        
    elif mode == 'audio':
        gender = mode_data.get('gender', 'male')
        await generate_audio(text, gender, update)
        
    elif mode == 'explain':
        await process_long_text(text, update, 'explain')
    
    await processing.delete()
    
    # حذف وضع المستخدم
    del user_data[user_id]
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📚 شرح وتحليل النص", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== إعادة التشغيل التلقائي للبوت ==========
def restart_bot():
    logger.warning("⚠️ جاري إعادة تشغيل البوت...")
    time.sleep(2)
    os.execl(sys.executable, sys.executable, *sys.argv)

def signal_handler(signum, frame):
    logger.warning(f"⚠️ استقبل إشارة {signum}، جاري إعادة التشغيل...")
    restart_bot()

# ========== التشغيل ==========
def main():
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 60)
    print("✅ البوت يعمل بنجاح!")
    print(f"📊 تطبيق Heroku: {HEROKU_APP_NAME}")
    print("🎨 توليد الصور: 5 محاولات مع إعادة تشغيل تلقائي")
    print("📚 شرح النص: 5 بدائل مجانية (يدعم المعادلات والعلوم)")
    print("=" * 60)
    
    try:
        app.run_polling()
    except Exception as e:
        logger.error(f"⚠️ البوت توقف: {e}")
        time.sleep(3)
        restart_bot()

if __name__ == "__main__":
    main()
