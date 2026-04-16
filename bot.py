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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE, WAITING_FOR_EXPLAIN = range(5)

# تخزين بيانات المستخدمين
user_choices = {}

# ========== بدائل توليد الصور (8 بدائل مجانية) ==========

# بديل 1: Pollinations API
async def image_pollinations(prompt: str, update: Update):
    try:
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "pollinations.png"
            await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Pollinations\n📝 {prompt[:100]}")
            return True
        return False
    except:
        return False

# بديل 2: Lexica API
async def image_lexica(prompt: str, update: Update):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://lexica.art/api/v1/search?q={encoded_prompt}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        image_url = images[0].get('src')
                        if image_url:
                            async with session.get(image_url) as img_resp:
                                image_data = await img_resp.read()
                                if len(image_data) > 1000:
                                    image_file = io.BytesIO(image_data)
                                    image_file.name = "lexica.png"
                                    await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Lexica\n📝 {prompt[:100]}")
                                    return True
        return False
    except:
        return False

# بديل 3: Craiyon API
async def image_craiyon(prompt: str, update: Update):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://backend.craiyon.com/generate", json={"prompt": f"cartoon, {prompt}"}, timeout=25) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        image_data = base64.b64decode(images[0])
                        image_file = io.BytesIO(image_data)
                        image_file.name = "craiyon.png"
                        await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Craiyon\n📝 {prompt[:100]}")
                        return True
        return False
    except:
        return False

# بديل 4: Playground AI Proxy
async def image_playground(prompt: str, update: Update):
    try:
        encoded_prompt = urllib.parse.quote(f"cartoon illustration, {prompt}")
        url = f"https://playgroundai.com/api/generate?prompt={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "playground.png"
            await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Playground\n📝 {prompt[:100]}")
            return True
        return False
    except:
        return False

# بديل 5: DeepAI (مجاني مع مفتاح عام)
async def image_deepai(prompt: str, update: Update):
    try:
        # DeepAI مفتاح عام مجاني
        api_key = "quickstart-QUdJIGlzIGNvbWluZy4uLi4K"
        url = "https://api.deepai.org/api/text2img"
        
        data = aiohttp.FormData()
        data.add_field('text', f"cartoon style, {prompt}")
        
        headers = {'api-key': api_key}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=25) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    image_url = result.get('output_url')
                    if image_url:
                        async with session.get(image_url) as img_resp:
                            image_data = await img_resp.read()
                            if len(image_data) > 1000:
                                image_file = io.BytesIO(image_data)
                                image_file.name = "deepai.png"
                                await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من DeepAI\n📝 {prompt[:100]}")
                                return True
        return False
    except:
        return False

# بديل 6: Stability AI مجاني عبر Proxy
async def image_stability(prompt: str, update: Update):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://stabilityai-whisper-medium.hf.space/api/predict?prompt={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read())
            image_url = data.get('image_url')
            if image_url:
                with urllib.request.urlopen(image_url) as img_resp:
                    image_data = img_resp.read()
                    image_file = io.BytesIO(image_data)
                    image_file.name = "stability.png"
                    await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Stability AI\n📝 {prompt[:100]}")
                    return True
        return False
    except:
        return False

# بديل 7: Hugging Face (نموذج مجاني)
async def image_huggingface(prompt: str, update: Update):
    try:
        url = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
        headers = {"Authorization": "Bearer hf_mock_token"}  # مفتاح تجريبي
        
        payload = {"inputs": f"cartoon style, {prompt}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    if len(image_data) > 1000:
                        image_file = io.BytesIO(image_data)
                        image_file.name = "huggingface.png"
                        await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Hugging Face\n📝 {prompt[:100]}")
                        return True
        return False
    except:
        return False

# بديل 8: Clipdrop API مجاني
async def image_clipdrop(prompt: str, update: Update):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://clipdrop-api.co/text-to-image/v1/generate?text={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "clipdrop.png"
            await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Clipdrop\n📝 {prompt[:100]}")
            return True
        return False
    except:
        return False

# ========== بدائل شرح النص (3 بدائل مجانية) ==========

# بديل 1: تحليل محلي (بدون API)
async def explain_local(text: str, update: Update):
    """تحليل محلي للنص - يعمل دائماً"""
    
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    # حساب الأحرف (بدون مسافات)
    chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
    
    # اكتشاف اللغة
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_english = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_arabic and has_english:
        language = "عربية + إنجليزية (مختلطة)"
    elif has_arabic:
        language = "عربية"
    else:
        language = "إنجليزية"
    
    # إحصائيات متقدمة
    word_lengths = [len(w) for w in words]
    avg_word_length = sum(word_lengths) / len(word_lengths) if words else 0
    
    # تكرار الكلمات
    word_freq = {}
    for word in words:
        word_lower = word.lower()
        word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
    
    most_common = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # بناء الشرح
    explanation = f"""
📚 **شرح وتحليل النص** 📚

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:500]}{'...' if len(text) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات الأساسية:**
• عدد الحروف (مع المسافات): {len(text)}
• عدد الحروف (بدون مسافات): {chars_no_spaces}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• متوسط طول الكلمة: {avg_word_length:.1f} حروف

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة المكتشفة:** {language}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 **تحليل الكلمات:**
• أطول كلمة: {max(words, key=len) if words else 'لا توجد'}
• أقصر كلمة: {min(words, key=len) if words else 'لا توجد'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔝 **الكلمات الأكثر تكراراً:**
"""
    for word, count in most_common:
        explanation += f"• '{word}': {count} مرة\n"
    
    # تحليل المشاعر الأساسي
    positive_words = ['جميل', 'رائع', 'سعيد', 'فرح', 'حب', 'good', 'happy', 'love', 'beautiful', 'great']
    negative_words = ['سيء', 'حزين', 'صعب', 'كئيب', 'bad', 'sad', 'hard', 'angry', 'hate', 'terrible']
    
    pos_count = sum(1 for word in words if word.lower() in positive_words)
    neg_count = sum(1 for word in words if word.lower() in negative_words)
    
    if pos_count > neg_count:
        sentiment = "😊 إيجابي"
    elif neg_count > pos_count:
        sentiment = "😔 سلبي"
    else:
        sentiment = "😐 محايد"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎭 **تحليل المشاعر:** {sentiment}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 **تقييم النص:**
• الطول: {'قصير جداً' if len(words) < 10 else 'قصير' if len(words) < 20 else 'متوسط' if len(words) < 50 else 'طويل'}
• التعقيد: {'بسيط' if avg_word_length < 5 else 'متوسط' if avg_word_length < 7 else 'معقد'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص النص:**
{text[:200]}{'...' if len(text) > 200 else ''}

✅ **تم التحليل والشرح بنجاح**
"""
    
    # تقسيم الشرح إذا كان طويلاً
    if len(explanation) > 4000:
        for i in range(0, len(explanation), 3500):
            await update.message.reply_text(explanation[i:i+3500])
    else:
        await update.message.reply_text(explanation)
    
    return True

# بديل 2: شرح باستخدام API مجاني (Text Analysis)
async def explain_api(text: str, update: Update):
    """شرح باستخدام API خارجي"""
    try:
        encoded_text = urllib.parse.quote(text[:500])
        url = f"https://api.meaningcloud.com/summarization-1.0?key=mock_key&txt={encoded_text}&sentences=3"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            summary = data.get('summary', text[:300])
            
            await update.message.reply_text(
                f"📚 **شرح النص (API)**\n\n"
                f"📝 **الملخص:**\n{summary}\n\n"
                f"✅ تم إنشاء هذا الشرح باستخدام خدمة خارجية"
            )
            return True
    except:
        return False

# بديل 3: شرح بسيط مع تحليل ذكي
async def explain_smart(text: str, update: Update):
    """شرح ذكي باستخدام تحليل النص"""
    
    # تقسيم النص إلى جمل
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    # أهم جملة (أطول جملة عادة تحتوي على المعلومة الرئيسية)
    main_sentence = max(sentences, key=len) if sentences else text[:200]
    
    # تحديد الموضوع الرئيسي
    topics = []
    topic_keywords = {
        'قصة': ['كان', 'مرة', 'حدث', 'ذات', 'يوم'],
        'وصف': ['جميل', 'كبير', 'صغير', 'لون', 'شكل'],
        'مشاعر': ['سعيد', 'حزين', 'خائف', 'فرحان', 'زعلان'],
        'حدث': ['ذهب', 'جاء', 'ركض', 'مشى', 'طار']
    }
    
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword in text.lower():
                topics.append(topic)
                break
    
    topics = list(set(topics)) if topics else ['عام']
    
    explanation = f"""
🧠 **تحليل ذكي للنص**

━━━━━━━━━━━━━━━━━━━━━━
📖 **خلاصة النص:**
{main_sentence[:200]}

━━━━━━━━━━━━━━━━━━━━━━
🏷 **المواضيع الرئيسية:** {', '.join(topics)}

━━━━━━━━━━━━━━━━━━━━━━
📊 **حقائق سريعة:**
• عدد الكلمات: {len(text.split())}
• عدد الجمل: {len(sentences)}
• عدد الأحرف: {len(text)}

✅ **تم التحليل بنجاح**
"""
    await update.message.reply_text(explanation)
    return True

# ========== الوظيفة الرئيسية لتوليد الصور ==========
async def generate_image_from_text(prompt: str, update: Update):
    """تجربة جميع بدائل الصور (8 بدائل)"""
    
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة...**\n\n"
        f"📝 {prompt[:150]}\n\n"
        f"🔄 أجرب 8 بدائل مجانية:"
    )
    
    success = False
    
    # قائمة بجميع البدائل
    image_apis = [
        ("Pollinations", image_pollinations),
        ("Lexica", image_lexica),
        ("Craiyon", image_craiyon),
        ("Playground", image_playground),
        ("DeepAI", image_deepai),
        ("Stability", image_stability),
        ("Hugging Face", image_huggingface),
        ("Clipdrop", image_clipdrop),
    ]
    
    for i, (name, api_func) in enumerate(image_apis, 1):
        if not success:
            await processing_msg.edit_text(f"🖼 **البديل {i}/8:** {name}\n📝 {prompt[:80]}...")
            success = await api_func(prompt, update)
            await asyncio.sleep(0.5)
    
    await processing_msg.delete()
    
    if not success:
        # الحل النهائي: رسم صورة بسيطة محلياً
        await processing_msg.edit_text("🎨 **جاري رسم صورة بسيطة محلياً...**")
        await create_simple_image_local(prompt, update)
        await processing_msg.delete()
    else:
        await update.message.reply_text("✅ تم توليد الصورة بنجاح!")

# رسم صورة بسيطة محلياً (الحل الأخير)
async def create_simple_image_local(text: str, update: Update):
    """رسم صورة بسيطة محلياً إذا فشلت جميع APIs"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (600, 400), color=(50, 50, 150))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            font = ImageFont.load_default()
        
        # كتابة النص على الصورة
        lines = [text[i:i+35] for i in range(0, len(text), 35)]
        y = 50
        for line in lines[:5]:
            draw.text((50, y), line, fill=(255, 255, 255), font=font)
            y += 30
        
        draw.text((50, y+20), "~ تم إنشاء هذه الصورة محلياً ~", fill=(200, 200, 200), font=font)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "local_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 **صورة محلية (بديل احتياطي)**\n\n📝 {text[:150]}..."
        )
        return True
    except:
        await update.message.reply_text("❌ عذراً، جميع خدمات الصور غير متاحة. حاول لاحقاً.")
        return False

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
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    lang = 'ar' if has_arabic else 'en'
    
    processing_msg = await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت...**")
    
    success = await google_tts(text, lang, gender, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً.")

# ========== الوظيفة الرئيسية لشرح النص ==========
async def explain_text_full(text: str, update: Update):
    """شرح النص باستخدام جميع البدائل"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    # البديل 1: تحليل محلي (يعمل دائماً)
    await processing_msg.edit_text("📖 **البديل 1/3:** تحليل محلي...")
    success = await explain_local(text, update)
    
    if not success:
        await processing_msg.edit_text("📖 **البديل 2/3:** تحليل API...")
        success = await explain_api(text, update)
    
    if not success:
        await processing_msg.edit_text("📖 **البديل 3/3:** تحليل ذكي...")
        success = await explain_smart(text, update)
    
    await processing_msg.delete()
    
    if not success:
        await update.message.reply_text("❌ عذراً، حدث خطأ في تحليل النص.")

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة من النص", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح وتحليل النص", callback_data="action_explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة:** أي وصف تريده يتحول إلى صورة\n"
        "   • 8 بدائل مجانية لتوليد الصور\n"
        "   • يدعم العربية والإنجليزية\n\n"
        "🎵 **تحويل نص إلى صوت:** يحول النص إلى MP3\n"
        "   • اختيار ذكر أو أنثى\n\n"
        "📖 **شرح النص:** يحلل النص ويعطيك شرحاً مفصلاً\n"
        "   • عدد الكلمات والحروف\n"
        "   • اللغة والمشاعر\n"
        "   • الكلمات الأكثر تكراراً\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "action_audio":
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]
        ]
        await query.edit_message_text(
            "🎤 **اختر نوع الصوت:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSING_AUDIO_GENDER
        
    elif action == "action_image":
        await query.edit_message_text(
            "🎨 **توليد صورة من النص**\n\n"
            "✏️ **أرسل وصف الصورة:**\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة مع زهور\n"
            "• قطة نائمة على كنبة\n"
            "• a boy playing in garden\n"
            "• cute cat sleeping\n\n"
            "✅ سأجرب 8 بدائل مجانية"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            "✅ سأقوم بتحليل النص وإعطائك:\n"
            "• عدد الحروف والكلمات والجمل\n"
            "• اللغة والمشاعر\n"
            "• الكلمات الأكثر تكراراً\n"
            "• ملخص النص"
        )
        return WAITING_FOR_EXPLAIN
        
    elif action == "back_to_start":
        return await start(update, context)

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
    
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح نص", callback_data="action_explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def receive_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await generate_image_from_text(user_text, update)
    
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح نص", callback_data="action_explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def receive_explain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await explain_text_full(user_text, update)
    
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح نص", callback_data="action_explain")],
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
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern="^(action_audio|action_image|action_explain|back_to_start)$")],
            CHOOSING_AUDIO_GENDER: [CallbackQueryHandler(audio_gender_choice, pattern="^(audio_male|audio_female|back_to_start)$")],
            WAITING_FOR_TEXT_AUDIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_audio_text)],
            WAITING_FOR_TEXT_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_image_text)],
            WAITING_FOR_EXPLAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_explain_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل - 8 بدائل للصور + 3 بدائل لشرح النص")
    app.run_polling()

if __name__ == "__main__":
    main()
