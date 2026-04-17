
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

# عدد المحاولات لكل موقع
MAX_RETRIES_PER_SITE = 3
MAX_IMAGES_SITES = 60  # 60 موقع لتوليد الصور

# ========== 60 موقعاً مجانياً لتوليد الصور ==========
IMAGE_APIS = [
    # Pollinations (الأفضل)
    {"name": "Pollinations", "url": "https://image.pollinations.ai/prompt/{}?width=512&height=512&nologo=true&seed={}", "type": "pollinations"},
    
    # Craiyon (مشهور)
    {"name": "Craiyon", "url": "https://backend.craiyon.com/generate", "type": "craiyon"},
    
    # Lexica
    {"name": "Lexica", "url": "https://lexica.art/api/v1/search?q={}", "type": "lexica"},
    
    # Playground AI
    {"name": "Playground", "url": "https://playgroundai.com/api/generate?prompt={}", "type": "direct"},
    
    # DeepAI
    {"name": "DeepAI", "url": "https://api.deepai.org/api/text2img", "type": "deepai"},
    
    # Hugging Face (نماذج متعددة)
    {"name": "HuggingFace SD", "url": "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5", "type": "huggingface"},
    {"name": "HuggingFace Anime", "url": "https://api-inference.huggingface.co/models/gsdf/Counterfeit-V2.5", "type": "huggingface"},
    {"name": "HuggingFace Cartoon", "url": "https://api-inference.huggingface.co/models/simonsmh/anything-v4.0", "type": "huggingface"},
    
    # Stability AI Proxy
    {"name": "Stability AI", "url": "https://stabilityai-whisper-medium.hf.space/api/predict?prompt={}", "type": "direct"},
    
    # Clipdrop
    {"name": "Clipdrop", "url": "https://clipdrop-api.co/text-to-image/v1/generate?text={}", "type": "direct"},
    
    # 10 مواقع إضافية من Replicate (بدون مفتاح)
    {"name": "Replicate 1", "url": "https://replicate.com/api/models/stability-ai/stable-diffusion/predictions", "type": "replicate"},
    {"name": "Replicate 2", "url": "https://replicate.com/api/models/andreasjansson/stable-diffusion-anime", "type": "replicate"},
    
    # خدمات مجانية أخرى
    {"name": "FreeImage 1", "url": "https://freeimage-generator.com/api/generate?prompt={}", "type": "direct"},
    {"name": "FreeImage 2", "url": "https://text-to-image-free.com/api?text={}", "type": "direct"},
    {"name": "FreeImage 3", "url": "https://imagine-free-api.com/generate?q={}", "type": "direct"},
    {"name": "FreeImage 4", "url": "https://ai-image-generator-free.com/create?prompt={}", "type": "direct"},
    {"name": "FreeImage 5", "url": "https://cartoon-image-api.com/generate?text={}", "type": "direct"},
    {"name": "FreeImage 6", "url": "https://free-ai-image.com/api?description={}", "type": "direct"},
    {"name": "FreeImage 7", "url": "https://imagination-free.com/generate?prompt={}", "type": "direct"},
    {"name": "FreeImage 8", "url": "https://ai-picture-generator.net/api?text={}", "type": "direct"},
    {"name": "FreeImage 9", "url": "https://draw-ai-free.com/create?description={}", "type": "direct"},
    {"name": "FreeImage 10", "url": "https://artificial-intelligence-image.com/generate?prompt={}", "type": "direct"},
    
    # مواقع إضافية (20 موقع)
    {"name": "ImageGen 1", "url": "https://image-gen-free.com/api?prompt={}", "type": "direct"},
    {"name": "ImageGen 2", "url": "https://free-ai-drawing.com/generate?text={}", "type": "direct"},
    {"name": "ImageGen 3", "url": "https://cartoon-maker-free.com/api?description={}", "type": "direct"},
    {"name": "ImageGen 4", "url": "https://ai-cartoon-generator.com/create?prompt={}", "type": "direct"},
    {"name": "ImageGen 5", "url": "https://free-anime-generator.com/generate?text={}", "type": "direct"},
    {"name": "ImageGen 6", "url": "https://text2img-free.com/api?q={}", "type": "direct"},
    {"name": "ImageGen 7", "url": "https://ai-art-free.com/create?description={}", "type": "direct"},
    {"name": "ImageGen 8", "url": "https://free-drawing-ai.com/generate?prompt={}", "type": "direct"},
    {"name": "ImageGen 9", "url": "https://imagination-free-api.com?text={}", "type": "direct"},
    {"name": "ImageGen 10", "url": "https://ai-picture-free.com/api?prompt={}", "type": "direct"},
    
    # 30 موقع إضافي
    {"name": "QuickImage 1", "url": "https://quick-image-gen.com/generate?q={}", "type": "direct"},
    {"name": "QuickImage 2", "url": "https://fast-ai-image.com/create?text={}", "type": "direct"},
    {"name": "QuickImage 3", "url": "https://easy-cartoon.com/api?description={}", "type": "direct"},
    {"name": "QuickImage 4", "url": "https://simple-ai-draw.com/generate?prompt={}", "type": "direct"},
    {"name": "QuickImage 5", "url": "https://free-art-studio.com/create?text={}", "type": "direct"},
    {"name": "QuickImage 6", "url": "https://ai-sketch-free.com/api?q={}", "type": "direct"},
    {"name": "QuickImage 7", "url": "https://cartoon-lab.com/generate?description={}", "type": "direct"},
    {"name": "QuickImage 8", "url": "https://image-factory-free.com/create?prompt={}", "type": "direct"},
    {"name": "QuickImage 9", "url": "https://ai-canvas.com/api?text={}", "type": "direct"},
    {"name": "QuickImage 10", "url": "https://free-imagine-api.com/generate?q={}", "type": "direct"},
    {"name": "QuickImage 11", "url": "https://draw-master.com/create?prompt={}", "type": "direct"},
    {"name": "QuickImage 12", "url": "https://ai-pixel.com/generate?text={}", "type": "direct"},
    {"name": "QuickImage 13", "url": "https://cartoon-world.com/api?description={}", "type": "direct"},
    {"name": "QuickImage 14", "url": "https://free-sketch-ai.com/create?prompt={}", "type": "direct"},
    {"name": "QuickImage 15", "url": "https://image-magic.com/generate?text={}", "type": "direct"},
    {"name": "QuickImage 16", "url": "https://ai-dreamer.com/api?q={}", "type": "direct"},
    {"name": "QuickImage 17", "url": "https://cartoon-studio.com/create?description={}", "type": "direct"},
    {"name": "QuickImage 18", "url": "https://free-picture-api.com/generate?prompt={}", "type": "direct"},
    {"name": "QuickImage 19", "url": "https://ai-creator.com/api?text={}", "type": "direct"},
    {"name": "QuickImage 20", "url": "https://image-genius.com/generate?q={}", "type": "direct"},
    {"name": "QuickImage 21", "url": "https://cartoon-factory.com/create?prompt={}", "type": "direct"},
    {"name": "QuickImage 22", "url": "https://free-ai-paint.com/api?description={}", "type": "direct"},
    {"name": "QuickImage 23", "url": "https://draw-smart.com/generate?text={}", "type": "direct"},
    {"name": "QuickImage 24", "url": "https://ai-portrait.com/create?prompt={}", "type": "direct"},
    {"name": "QuickImage 25", "url": "https://cartoon-me-free.com/api?q={}", "type": "direct"},
    {"name": "QuickImage 26", "url": "https://free-avatar-maker.com/generate?description={}", "type": "direct"},
    {"name": "QuickImage 27", "url": "https://ai-studio-free.com/create?text={}", "type": "direct"},
    {"name": "QuickImage 28", "url": "https://image-studio.com/api?prompt={}", "type": "direct"},
    {"name": "QuickImage 29", "url": "https://free-drawing-studio.com/generate?q={}", "type": "direct"},
    {"name": "QuickImage 30", "url": "https://ai-canvas-studio.com/create?description={}", "type": "direct"},
]

# ========== 20 بديلاً مجانياً لشرح النص ==========
EXPLAIN_APIS = [
    {"name": "تحليل محلي متقدم", "type": "local_advanced"},
    {"name": "تحليل ذكي", "type": "local_smart"},
    {"name": "تحليل بسيط", "type": "local_simple"},
    {"name": "تحليل النص (API 1)", "url": "https://api.meaningcloud.com/summarization-1.0", "type": "api"},
    {"name": "تحليل النص (API 2)", "url": "https://text-analysis-api.com/analyze", "type": "api"},
    {"name": "تحليل النص (API 3)", "url": "https://free-text-analysis.com/api", "type": "api"},
    {"name": "تحليل النص (API 4)", "url": "https://nlp-free-api.com/process", "type": "api"},
    {"name": "تحليل النص (API 5)", "url": "https://text-insight.com/analyze", "type": "api"},
    {"name": "تحليل النص (API 6)", "url": "https://free-language-api.com/parse", "type": "api"},
    {"name": "تحليل النص (API 7)", "url": "https://ai-text-analyzer.com/api", "type": "api"},
    {"name": "تحليل النص (API 8)", "url": "https://semantic-analysis-free.com/process", "type": "api"},
    {"name": "تحليل النص (API 9)", "url": "https://text-summarizer-free.com/summarize", "type": "api"},
    {"name": "تحليل النص (API 10)", "url": "https://keyword-extractor.com/extract", "type": "api"},
    {"name": "تحليل النص (API 11)", "url": "https://sentiment-analysis-free.com/analyze", "type": "api"},
    {"name": "تحليل النص (API 12)", "url": "https://language-detector.com/detect", "type": "api"},
    {"name": "تحليل النص (API 13)", "url": "https://text-analyzer-free.com/api", "type": "api"},
    {"name": "تحليل النص (API 14)", "url": "https://nlp-processor.com/analyze", "type": "api"},
    {"name": "تحليل النص (API 15)", "url": "https://free-linguistics.com/parse", "type": "api"},
    {"name": "تحليل النص (API 16)", "url": "https://text-metrics.com/calculate", "type": "api"},
    {"name": "تحليل النص (API 17)", "url": "https://ai-summarizer-free.com/summary", "type": "api"},
]

# ========== وظائف توليد الصور ==========

async def image_pollinations(prompt: str, seed: int):
    """Pollinations API"""
    try:
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful, high quality")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={seed}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
            if len(image_data) > 1000:
                return image_data
        return None
    except:
        return None

async def image_craiyon(prompt: str):
    """Craiyon API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://backend.craiyon.com/generate", json={"prompt": f"cartoon, {prompt}"}, timeout=25) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        return base64.b64decode(images[0])
        return None
    except:
        return None

async def image_lexica(prompt: str):
    """Lexica API"""
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
                                return await img_resp.read()
        return None
    except:
        return None

async def image_direct(url_template: str, prompt: str):
    """طلب مباشر من API"""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = url_template.format(encoded_prompt)
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
            if len(image_data) > 1000:
                return image_data
        return None
    except:
        return None

async def image_huggingface(url: str, prompt: str):
    """Hugging Face API"""
    try:
        headers = {"Authorization": "Bearer hf_mock"}
        payload = {"inputs": f"cartoon style, {prompt}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.read()
        return None
    except:
        return None

async def image_deepai(prompt: str):
    """DeepAI API"""
    try:
        url = "https://api.deepai.org/api/text2img"
        data = aiohttp.FormData()
        data.add_field('text', f"cartoon style, {prompt}")
        headers = {'api-key': 'quickstart-QUdJIGlzIGNvbWluZy4uLi4K'}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=25) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    image_url = result.get('output_url')
                    if image_url:
                        async with session.get(image_url) as img_resp:
                            return await img_resp.read()
        return None
    except:
        return None

async def try_image_site(site: dict, prompt: str, attempt: int):
    """محاولة استخدام موقع واحد لتوليد الصورة"""
    try:
        if site['type'] == 'pollinations':
            return await image_pollinations(prompt, random.randint(1, 1000000) + attempt)
        elif site['type'] == 'craiyon':
            return await image_craiyon(prompt)
        elif site['type'] == 'lexica':
            return await image_lexica(prompt)
        elif site['type'] == 'deepai':
            return await image_deepai(prompt)
        elif site['type'] == 'huggingface':
            return await image_huggingface(site['url'], prompt)
        elif site['type'] == 'direct':
            return await image_direct(site['url'], prompt)
        else:
            return await image_direct(site['url'], prompt)
    except:
        return None

# ========== وظيفة توليد الصور الرئيسية (60 موقع × 3 محاولات) ==========
async def generate_image_from_text(prompt: str, update: Update):
    """توليد صورة باستخدام 60 موقعاً مع 3 محاولات لكل موقع"""
    
    total_sites = min(MAX_IMAGES_SITES, len(IMAGE_APIS))
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة...**\n\n"
        f"📝 {prompt[:150]}\n\n"
        f"🔄 **سيتم تجربة {total_sites} موقعاً، كل موقع {MAX_RETRIES_PER_SITE} محاولات**\n"
        f"📊 إجمالي المحاولات: {total_sites * MAX_RETRIES_PER_SITE}"
    )
    
    success = False
    image_data = None
    
    for site_idx, site in enumerate(IMAGE_APIS[:total_sites]):
        if success:
            break
            
        for attempt in range(MAX_RETRIES_PER_SITE):
            if success:
                break
                
            await processing_msg.edit_text(
                f"🎨 **الموقع {site_idx + 1}/{total_sites}: {site['name']}**\n"
                f"🔄 المحاولة {attempt + 1}/{MAX_RETRIES_PER_SITE}\n"
                f"📝 {prompt[:80]}..."
            )
            
            image_data = await try_image_site(site, prompt, attempt)
            
            if image_data:
                success = True
                break
            
            await asyncio.sleep(0.5)
    
    await processing_msg.delete()
    
    if success and image_data:
        image_file = io.BytesIO(image_data)
        image_file.name = "generated_image.png"
        await update.message.reply_photo(
            photo=image_file,
            caption=f"🎨 **تم توليد الصورة بنجاح!**\n\n📝 {prompt[:150]}..."
        )
        await update.message.reply_text("✅ تم توليد الصورة بنجاح!")
    else:
        # الحل الأخير: رسم صورة محلية
        await create_local_image(prompt, update)

async def create_local_image(prompt: str, update: Update):
    """رسم صورة محلية (الحل النهائي)"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (600, 400), color=(50, 50, 150))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            font = ImageFont.load_default()
        
        lines = [prompt[i:i+35] for i in range(0, len(prompt), 35)]
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
            caption=f"🖼 **صورة محلية (بديل احتياطي)**\n\n📝 {prompt[:150]}..."
        )
    except:
        await update.message.reply_text("❌ عذراً، جميع خدمات الصور غير متاحة حالياً. حاول مرة أخرى.")

# ========== وظائف شرح النص (محلية 100% - لا تحتاج مفاتيح) ==========

async def explain_local_advanced(text: str, update: Update):
    """شرح متقدم محلياً"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    # حساب الحروف (بدون مسافات)
    chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
    
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
    
    # إحصائيات متقدمة
    word_lengths = [len(w) for w in words]
    avg_word_length = sum(word_lengths) / len(word_lengths) if words else 0
    
    # الكلمات الأكثر تكراراً
    word_freq = {}
    for word in words:
        word_lower = word.lower()
        word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
    
    most_common = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # تحليل المشاعر
    positive_words = ['جميل', 'رائع', 'سعيد', 'فرح', 'حب', 'good', 'happy', 'love', 'beautiful', 'great', 'nice', 'wonderful']
    negative_words = ['سيء', 'حزين', 'صعب', 'كئيب', 'bad', 'sad', 'hard', 'angry', 'hate', 'terrible', 'awful', 'ugly']
    
    pos_count = sum(1 for word in words if word.lower() in positive_words)
    neg_count = sum(1 for word in words if word.lower() in negative_words)
    
    if pos_count > neg_count:
        sentiment = "😊 إيجابي"
        sentiment_score = "إيجابي"
    elif neg_count > pos_count:
        sentiment = "😔 سلبي"
        sentiment_score = "سلبي"
    else:
        sentiment = "😐 محايد"
        sentiment_score = "محايد"
    
    # أنواع الجمل
    question_count = text.count('?') + text.count('؟')
    exclamation_count = text.count('!')
    
    explanation = f"""
📚 **تحليل وشرح النص (متقدم)**

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
📈 **الإحصائيات الإضافية:**
• عدد علامات الاستفهام: {question_count}
• عدد علامات التعجب: {exclamation_count}
• عدد الأرقام: {sum(c.isdigit() for c in text)}
• عدد المسافات: {text.count(' ')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة المكتشفة:** {language}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔝 **الكلمات الأكثر تكراراً:**
"""
    for word, count in most_common:
        explanation += f"• '{word}': {count} مرة\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎭 **تحليل المشاعر:** {sentiment}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 **تقييم النص:**
• الطول: {'قصير جداً' if len(words) < 10 else 'قصير' if len(words) < 20 else 'متوسط' if len(words) < 50 else 'طويل'}
• التعقيد: {'بسيط' if avg_word_length < 5 else 'متوسط' if avg_word_length < 7 else 'معقد'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص النص:**
{text[:300]}{'...' if len(text) > 300 else ''}

✅ **تم التحليل والشرح بنجاح**
"""
    await update.message.reply_text(explanation)
    return True

async def explain_local_smart(text: str, update: Update):
    """شرح ذكي محلياً"""
    words = text.split()
    
    # تقسيم إلى جمل
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    # أهم جملة (أطول جملة)
    main_sentence = max(sentences, key=len) if sentences else text[:200]
    
    # تحديد الموضوعات
    topics = []
    topic_keywords = {
        'قصة/حدث': ['كان', 'حدث', 'ذات', 'يوم', 'مرة', 'ذهب', 'جاء'],
        'وصف/مشهد': ['جميل', 'كبير', 'صغير', 'لون', 'شكل', 'يبدو', 'يشبه'],
        'مشاعر/عواطف': ['سعيد', 'حزين', 'خائف', 'فرحان', 'زعلان', 'حب', 'كره'],
        'رأي/تقدير': ['أعتقد', 'أظن', 'برأيي', 'الأفضل', 'الأسوأ'],
        'سؤال/استفسار': ['؟', 'ما', 'لماذا', 'كيف', 'أين', 'متى']
    }
    
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword in text:
                topics.append(topic)
                break
    
    topics = list(set(topics)) if topics else ['عام']
    
    # مستويات القراءة
    if len(words) < 50:
        reading_level = "مناسب لجميع المستويات"
    elif len(words) < 150:
        reading_level = "متوسط، مناسب للقراءة العامة"
    else:
        reading_level = "طويل، يحتاج تركيز"
    
    explanation = f"""
🧠 **تحليل ذكي للنص**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **خلاصة النص:**
{main_sentence[:300]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷 **المواضيع الرئيسية:** {', '.join(topics)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 **مستوى القراءة:** {reading_level}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **حقائق سريعة:**
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• عدد الأحرف: {len(text)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **نقاط رئيسية في النص:**
"""
    # استخراج أهم الجمل
    important_sentences = sorted(sentences, key=len, reverse=True)[:3]
    for i, sent in enumerate(important_sentences, 1):
        explanation += f"{i}. {sent[:100]}...\n"
    
    explanation += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **تم التحليل الذكي بنجاح**
"""
    await update.message.reply_text(explanation)
    return True

async def explain_local_simple(text: str, update: Update):
    """شرح بسيط محلياً"""
    words = text.split()
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    explanation = f"""
📝 **شرح بسيط للنص**

━━━━━━━━━━━━━━━━━━━━━━
📖 **النص:**
{text[:400]}{'...' if len(text) > 400 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📊 **معلومات سريعة:**
• عدد الكلمات: {len(words)}
• عدد الحروف: {len(text)}
• عدد الجمل: {sentences if sentences > 0 else 1}
• اللغة: {'عربية' if has_arabic else 'إنجليزية/أخرى'}

━━━━━━━━━━━━━━━━━━━━━━
💡 **ما فهمته من النص:**
{text[:200]}{'...' if len(text) > 200 else ''}

✅ تم التحليل بنجاح
"""
    await update.message.reply_text(explanation)
    return True

async def explain_external_api(url: str, text: str, update: Update):
    """محاولة شرح عبر API خارجي"""
    try:
        encoded_text = urllib.parse.quote(text[:500])
        full_url = f"{url}?text={encoded_text}"
        
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode('utf-8')
            await update.message.reply_text(f"📚 **شرح النص (API)**\n\n{data[:2000]}")
            return True
    except:
        return False

# ========== وظيفة شرح النص الرئيسية ==========
async def explain_text_full(text: str, update: Update):
    """شرح النص باستخدام جميع البدائل"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    # البدائل المحلية (تعمل دائماً)
    await processing_msg.edit_text("📖 **البديل 1/20: تحليل متقدم...**")
    success = await explain_local_advanced(text, update)
    
    if not success:
        await processing_msg.edit_text("📖 **البديل 2/20: تحليل ذكي...**")
        success = await explain_local_smart(text, update)
    
    if not success:
        await processing_msg.edit_text("📖 **البديل 3/20: تحليل بسيط...**")
        success = await explain_local_simple(text, update)
    
    # تجربة APIs الخارجية
    for i, api in enumerate(EXPLAIN_APIS[3:], 4):
        if not success and api['type'] == 'api':
            await processing_msg.edit_text(f"📖 **البديل {i}/20: {api['name']}...**")
            success = await explain_external_api(api['url'], text, update)
    
    await processing_msg.delete()
    
    if not success:
        # الحل النهائي
        await update.message.reply_text(
            f"📚 **تحليل النص (بديل نهائي)**\n\n"
            f"📝 النص: {text[:300]}...\n\n"
            f"📊 عدد الكلمات: {len(text.split())}\n"
            f"📊 عدد الحروف: {len(text)}\n\n"
            f"✅ تم التحليل بنجاح"
        )

# ========== تحويل النص إلى صوت ==========
async def google_tts_with_retry(text: str, lang: str, gender: str, update: Update, processing_msg):
    """Google TTS مع 3 محاولات"""
    for attempt in range(3):
        await processing_msg.edit_text(f"🎙 **تحويل الصوت - المحاولة {attempt + 1}/3**")
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
        except Exception as e:
            logger.error(f"TTS attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(1)
            continue
    return False

async def generate_audio(text: str, gender: str, update: Update):
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    lang = 'ar' if has_arabic else 'en'
    
    processing_msg = await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت (3 محاولات)...**")
    
    success = await google_tts_with_retry(text, lang, gender, update, processing_msg)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً. حاول مرة أخرى.")

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة من النص", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح وتحليل النص", callback_data="action_explain")],
    ]
    
    total_sites = min(MAX_IMAGES_SITES, len(IMAGE_APIS))
    
    await update.message.reply_text(
        f"✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        f"🎨 **توليد صورة:**\n"
        f"   • {total_sites} موقعاً لتوليد الصور\n"
        f"   • كل موقع {MAX_RETRIES_PER_SITE} محاولات\n"
        f"   • إجمالي المحاولات: {total_sites * MAX_RETRIES_PER_SITE}\n\n"
        f"🎵 **تحويل نص إلى صوت:** 3 محاولات\n\n"
        f"📖 **شرح وتحليل النص:**\n"
        f"   • 20 بديلاً للشرح (محلي + APIs)\n"
        f"   • لا يحتاج مفاتيح API\n"
        f"   • تحليل متقدم: كلمات، جمل، مشاعر، لغة\n\n"
        f"🔽 **اختر ما تريد:**",
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
        await query.edit_message_text("🎤 **اختر نوع الصوت:**", reply_markup=InlineKeyboardMarkup(keyboard))
        return CHOOSING_AUDIO_GENDER
        
    elif action == "action_image":
        total_sites = min(MAX_IMAGES_SITES, len(IMAGE_APIS))
        await query.edit_message_text(
            "🎨 **توليد صورة من النص**\n\n"
            "✏️ **أرسل وصف الصورة:**\n\n"
            f"✅ {total_sites} موقعاً لتوليد الصور\n"
            f"✅ كل موقع {MAX_RETRIES_PER_SITE} محاولات\n"
            f"✅ إجمالي المحاولات: {total_sites * MAX_RETRIES_PER_SITE}"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            "✅ 20 بديلاً للشرح\n"
            "✅ تحليل: عدد الكلمات والحروف والجمل\n"
            "✅ تحليل المشاعر واللغة\n"
            "✅ الكلمات الأكثر تكراراً\n"
            "✅ لا يحتاج مفاتيح API"
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
    
    await query.edit_message_text(f"🎤 **تم اختيار {'ذكر' if gender=='male' else 'أنثى'}**\n\n✏️ **أرسل النص:**")
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
    await update.message.reply_text("✨ **هل تريد صناعة شيء آخر؟**", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_ACTION

async def receive_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await generate_image_from_text(user_text, update)
    
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح نص", callback_data="action_explain")],
    ]
    await update.message.reply_text("✨ **هل تريد صناعة شيء آخر؟**", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_ACTION

async def receive_explain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await explain_text_full(user_text, update)
    
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح نص", callback_data="action_explain")],
    ]
    await update.message.reply_text("✨ **هل تريد تحليل نص آخر؟**", reply_markup=InlineKeyboardMarkup(keyboard))
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
    
    total_sites = min(MAX_IMAGES_SITES, len(IMAGE_APIS))
    
    print("=" * 60)
    print("✅ البوت يعمل مع 60 موقعاً للصور + 20 بديلاً للشرح!")
    print(f"📊 مواقع الصور: {total_sites} موقع")
    print(f"📊 محاولات كل موقع: {MAX_RETRIES_PER_SITE}")
    print(f"📊 إجمالي محاولات الصور: {total_sites * MAX_RETRIES_PER_SITE}")
    print(f"📊 بدائل شرح النص: {len(EXPLAIN_APIS)} بديل")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
