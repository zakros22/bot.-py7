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

# ========== مفاتيح API من Heroku ==========
# DeepSeek Keys (deepseek_key1 إلى deepseek_key9)
DEEPSEEK_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"DEEPSEEK_KEY{i}")
    if key:
        DEEPSEEK_KEYS.append(key)

# Gemini Keys (gemini_key1 إلى gemini_key9)
GEMINI_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"GEMINI_KEY{i}")
    if key:
        GEMINI_KEYS.append(key)

# OpenRouter Keys (openrouter_key1 إلى openrouter_key9)
OPENROUTER_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"OPENROUTER_KEY{i}")
    if key:
        OPENROUTER_KEYS.append(key)

# إعدادات المحاولات
MAX_RETRIES_POLLINATIONS = 10      # عدد محاولات Pollinations
MAX_RETRIES_BACKUP_IMAGE = 3       # عدد محاولات كل بديل صور احتياطي
MAX_RETRIES_API = 5                # عدد محاولات كل مفتاح API للشرح

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE, WAITING_FOR_EXPLAIN = range(5)

# تخزين بيانات المستخدمين
user_choices = {}

# تخزين حالة المفاتيح
key_states = {
    'deepseek': {'keys': DEEPSEEK_KEYS, 'current_index': 0, 'failed_keys': set(), 'retry_count': 0},
    'gemini': {'keys': GEMINI_KEYS, 'current_index': 0, 'failed_keys': set(), 'retry_count': 0},
    'openrouter': {'keys': OPENROUTER_KEYS, 'current_index': 0, 'failed_keys': set(), 'retry_count': 0}
}

# ========== وظيفة المحاولة مع إعادة التجربة ==========
async def retry_request(func, *args, max_retries=3, delay=1, **kwargs):
    """تنفيذ طلب مع إعادة المحاولة تلقائياً"""
    for attempt in range(max_retries):
        try:
            result = await func(*args, **kwargs)
            if result:
                return True
        except Exception as e:
            logger.warning(f"محاولة {attempt + 1}/{max_retries} فشلت: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(delay * (attempt + 1))  # تأخير متزايد
    return False

# ========== توليد الصور باستخدام Pollinations (مع 10 محاولات) ==========
async def image_pollinations_with_retry(prompt: str, update: Update, processing_msg):
    """Pollinations مع 10 محاولات"""
    
    for attempt in range(MAX_RETRIES_POLLINATIONS):
        await processing_msg.edit_text(
            f"🎨 **Pollinations - المحاولة {attempt + 1}/{MAX_RETRIES_POLLINATIONS}**\n\n"
            f"📝 {prompt[:100]}...\n\n"
            f"🔄 جاري التوليد..."
        )
        
        try:
            clean_prompt = prompt.strip().replace(" ", "%20")
            encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful, high quality")
            random_seed = random.randint(1, 1000000)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={random_seed}"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
            
            if len(image_data) > 1000:
                image_file = io.BytesIO(image_data)
                image_file.name = "pollinations.png"
                await update.message.reply_photo(
                    photo=image_file,
                    caption=f"🎨 **صورة من Pollinations AI**\n\n📝 **الوصف:** {prompt[:150]}...\n\n✅ تم التوليد بنجاح بعد {attempt + 1} محاولة!"
                )
                return True
                
        except Exception as e:
            logger.error(f"Pollinations محاولة {attempt + 1} فشلت: {e}")
            if attempt < MAX_RETRIES_POLLINATIONS - 1:
                await asyncio.sleep(2)  # انتظار قبل المحاولة التالية
            continue
    
    return False

# ========== بدائل الصور الاحتياطية (مع 3 محاولات لكل بديل) ==========

async def image_craiyon_with_retry(prompt: str, update: Update, processing_msg):
    """Craiyon مع 3 محاولات"""
    for attempt in range(MAX_RETRIES_BACKUP_IMAGE):
        await processing_msg.edit_text(f"🖼 **Craiyon - المحاولة {attempt + 1}/{MAX_RETRIES_BACKUP_IMAGE}**")
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
                            await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Craiyon (بديل)\n📝 {prompt[:100]}")
                            return True
        except Exception as e:
            logger.error(f"Craiyon محاولة {attempt + 1} فشلت: {e}")
            if attempt < MAX_RETRIES_BACKUP_IMAGE - 1:
                await asyncio.sleep(1)
            continue
    return False

async def image_lexica_with_retry(prompt: str, update: Update, processing_msg):
    """Lexica مع 3 محاولات"""
    for attempt in range(MAX_RETRIES_BACKUP_IMAGE):
        await processing_msg.edit_text(f"🖼 **Lexica - المحاولة {attempt + 1}/{MAX_RETRIES_BACKUP_IMAGE}**")
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
                                        await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Lexica (بديل)\n📝 {prompt[:100]}")
                                        return True
        except Exception as e:
            logger.error(f"Lexica محاولة {attempt + 1} فشلت: {e}")
            if attempt < MAX_RETRIES_BACKUP_IMAGE - 1:
                await asyncio.sleep(1)
            continue
    return False

async def image_local_fallback(prompt: str, update: Update, processing_msg):
    """رسم محلي (الحل الأخير)"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        await processing_msg.edit_text("🎨 **جاري رسم صورة محلية...**")
        
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
        img_buffer.name = "fallback_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 **صورة احتياطية (محلية)**\n\n📝 {prompt[:150]}...\n\n⚠️ جميع خدمات الصور غير متاحة حالياً."
        )
        return True
    except Exception as e:
        logger.error(f"Local fallback error: {e}")
        return False

# ========== وظيفة توليد الصور الرئيسية ==========
async def generate_image_from_text(prompt: str, update: Update):
    """توليد صورة مع 10 محاولات لـ Pollinations أولاً"""
    
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة...**\n\n"
        f"📝 {prompt[:150]}\n\n"
        f"🔄 **سيتم المحاولة {MAX_RETRIES_POLLINATIONS} مرة على Pollinations**"
    )
    
    success = False
    
    # الأولوية: Pollinations (10 محاولات)
    success = await image_pollinations_with_retry(prompt, update, processing_msg)
    
    # إذا فشل Pollinations، جرب البدائل الاحتياطية
    if not success:
        await processing_msg.edit_text("⚠️ **Pollinations غير متاح بعد 10 محاولات، أجرب بدائل احتياطية...**")
        
        # بديل 1: Craiyon (3 محاولات)
        success = await image_craiyon_with_retry(prompt, update, processing_msg)
        
        # بديل 2: Lexica (3 محاولات)
        if not success:
            success = await image_lexica_with_retry(prompt, update, processing_msg)
        
        # بديل 3: رسم محلي
        if not success:
            success = await image_local_fallback(prompt, update, processing_msg)
    
    await processing_msg.delete()
    
    if not success:
        await update.message.reply_text("❌ عذراً، جميع خدمات الصور غير متاحة. حاول مرة أخرى لاحقاً.")

# ========== شرح النص باستخدام DeepSeek (مع 5 محاولات لكل مفتاح) ==========

async def call_deepseek_with_retry(prompt: str, update: Update, processing_msg):
    """DeepSeek مع 5 محاولات لكل مفتاح"""
    keys_list = key_states['deepseek']['keys']
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['deepseek']['failed_keys']:
            continue
        
        for attempt in range(MAX_RETRIES_API):
            await processing_msg.edit_text(
                f"📖 **DeepSeek - المفتاح {key_idx + 1}/{len(keys_list)} - المحاولة {attempt + 1}/{MAX_RETRIES_API}**"
            )
            
            try:
                url = "https://api.deepseek.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "أنت مساعد ذكي متخصص في تحليل وشرح النصوص. قم بتحليل النص التالي وشرحه بشكل مفصل باللغة العربية."},
                        {"role": "user", "content": f"قم بتحليل وشرح هذا النص بشكل مفصل:\n\n{prompt}"}
                    ],
                    "max_tokens": 2000
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            explanation = result['choices'][0]['message']['content']
                            await update.message.reply_text(f"📚 **شرح DeepSeek AI**\n\n{explanation}")
                            return True
                        else:
                            logger.warning(f"DeepSeek key {key_idx + 1} attempt {attempt + 1} failed with status {resp.status}")
                            
            except Exception as e:
                logger.error(f"DeepSeek key {key_idx + 1} attempt {attempt + 1} error: {e}")
            
            if attempt < MAX_RETRIES_API - 1:
                await asyncio.sleep(2)  # انتظار بين المحاولات
        
        # إذا فشلت كل محاولات هذا المفتاح، ضعه في قائمة الفاشلة
        key_states['deepseek']['failed_keys'].add(key_idx)
        logger.warning(f"DeepSeek key {key_idx + 1} failed after {MAX_RETRIES_API} attempts")
    
    return False

async def call_gemini_with_retry(prompt: str, update: Update, processing_msg):
    """Gemini مع 5 محاولات لكل مفتاح"""
    keys_list = key_states['gemini']['keys']
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['gemini']['failed_keys']:
            continue
        
        for attempt in range(MAX_RETRIES_API):
            await processing_msg.edit_text(
                f"📖 **Gemini - المفتاح {key_idx + 1}/{len(keys_list)} - المحاولة {attempt + 1}/{MAX_RETRIES_API}**"
            )
            
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                data = {
                    "contents": [{
                        "parts": [{"text": f"قم بتحليل وشرح هذا النص بشكل مفصل باللغة العربية:\n\n{prompt}"}]
                    }]
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            explanation = result['candidates'][0]['content']['parts'][0]['text']
                            await update.message.reply_text(f"📚 **شرح Gemini AI**\n\n{explanation}")
                            return True
                        else:
                            logger.warning(f"Gemini key {key_idx + 1} attempt {attempt + 1} failed")
                            
            except Exception as e:
                logger.error(f"Gemini key {key_idx + 1} attempt {attempt + 1} error: {e}")
            
            if attempt < MAX_RETRIES_API - 1:
                await asyncio.sleep(2)
        
        key_states['gemini']['failed_keys'].add(key_idx)
    
    return False

async def call_openrouter_with_retry(prompt: str, update: Update, processing_msg):
    """OpenRouter مع 5 محاولات لكل مفتاح"""
    keys_list = key_states['openrouter']['keys']
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['openrouter']['failed_keys']:
            continue
        
        for attempt in range(MAX_RETRIES_API):
            await processing_msg.edit_text(
                f"📖 **OpenRouter - المفتاح {key_idx + 1}/{len(keys_list)} - المحاولة {attempt + 1}/{MAX_RETRIES_API}**"
            )
            
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "openai/gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "أنت مساعد متخصص في تحليل النصوص."},
                        {"role": "user", "content": f"حلل واشرح هذا النص باللغة العربية:\n\n{prompt}"}
                    ]
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            explanation = result['choices'][0]['message']['content']
                            await update.message.reply_text(f"📚 **شرح OpenRouter AI**\n\n{explanation}")
                            return True
                        else:
                            logger.warning(f"OpenRouter key {key_idx + 1} attempt {attempt + 1} failed")
                            
            except Exception as e:
                logger.error(f"OpenRouter key {key_idx + 1} attempt {attempt + 1} error: {e}")
            
            if attempt < MAX_RETRIES_API - 1:
                await asyncio.sleep(2)
        
        key_states['openrouter']['failed_keys'].add(key_idx)
    
    return False

# شرح محلي (البديل النهائي)
async def explain_local_fallback(text: str, update: Update):
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    explanation = f"""
📚 **شرح وتحليل النص (محلي - بديل احتياطي)**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:400]}{'...' if len(text) > 400 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص:**
{text[:200]}{'...' if len(text) > 200 else ''}

⚠️ جميع خدمات الشرح غير متاحة حالياً. هذا تحليل محلي بسيط.
"""
    await update.message.reply_text(explanation)
    return True

# الوظيفة الرئيسية لشرح النص
async def explain_text_full(text: str, update: Update):
    """شرح النص مع 5 محاولات لكل مفتاح"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    # الأولوية: DeepSeek (5 محاولات لكل مفتاح)
    if DEEPSEEK_KEYS and not success:
        success = await call_deepseek_with_retry(text, update, processing_msg)
    
    # الثاني: Gemini (5 محاولات لكل مفتاح)
    if GEMINI_KEYS and not success:
        success = await call_gemini_with_retry(text, update, processing_msg)
    
    # الثالث: OpenRouter (5 محاولات لكل مفتاح)
    if OPENROUTER_KEYS and not success:
        success = await call_openrouter_with_retry(text, update, processing_msg)
    
    # الأخير: شرح محلي
    if not success:
        await processing_msg.edit_text("📖 **جميع الخدمات غير متاحة، جاري التحليل المحلي...**")
        success = await explain_local_fallback(text, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحليل وشرح النص بنجاح!")

# ========== تحويل النص إلى صوت (مع 3 محاولات) ==========
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
    
    await update.message.reply_text(
        f"✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        f"🎨 **توليد صورة:**\n"
        f"   • Pollinations: {MAX_RETRIES_POLLINATIONS} محاولة\n"
        f"   • بدائل احتياطية: {MAX_RETRIES_BACKUP_IMAGE} محاولات لكل بديل\n\n"
        f"🎵 **تحويل نص إلى صوت:** 3 محاولات\n\n"
        f"📖 **شرح وتحليل النص:**\n"
        f"   • DeepSeek: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
        f"   • Gemini: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
        f"   • OpenRouter: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
        f"   • مفاتيح متاحة: DeepSeek({len(DEEPSEEK_KEYS)}), Gemini({len(GEMINI_KEYS)}), OpenRouter({len(OPENROUTER_KEYS)})\n\n"
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
        await query.edit_message_text(
            "🎨 **توليد صورة من النص**\n\n"
            "✏️ **أرسل وصف الصورة:**\n\n"
            f"✅ الأولوية لـ Pollinations ({MAX_RETRIES_POLLINATIONS} محاولة)\n"
            f"✅ ثم بدائل احتياطية ({MAX_RETRIES_BACKUP_IMAGE} محاولات لكل بديل)"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            f"✅ DeepSeek: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
            f"✅ Gemini: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
            f"✅ OpenRouter: {MAX_RETRIES_API} محاولات لكل مفتاح\n"
            f"📊 المفاتيح: DeepSeek({len(DEEPSEEK_KEYS)}), Gemini({len(GEMINI_KEYS)}), OpenRouter({len(OPENROUTER_KEYS)})"
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
    
    print("=" * 60)
    print("✅ البوت يعمل مع نظام المحاولات!")
    print(f"📊 Pollinations: {MAX_RETRIES_POLLINATIONS} محاولة")
    print(f"📊 البدائل الاحتياطية: {MAX_RETRIES_BACKUP_IMAGE} محاولات لكل بديل")
    print(f"📊 DeepSeek Keys: {len(DEEPSEEK_KEYS)} (كل مفتاح {MAX_RETRIES_API} محاولات)")
    print(f"📊 Gemini Keys: {len(GEMINI_KEYS)} (كل مفتاح {MAX_RETRIES_API} محاولات)")
    print(f"📊 OpenRouter Keys: {len(OPENROUTER_KEYS)} (كل مفتاح {MAX_RETRIES_API} محاولات)")
    print("=" * 60)
    app.run_polling()

if __name__ == "__main__":
    main()
