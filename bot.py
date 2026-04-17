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
import sys
import signal
import time
from datetime import datetime
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

# تخزين حالة المحاولات لكل مستخدم
user_retry_state = {}

# ========== مفاتيح API من Heroku ==========
DEEPSEEK_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"DEEPSEEK_KEY{i}")
    if key:
        DEEPSEEK_KEYS.append(key)

GEMINI_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"GEMINI_KEY{i}")
    if key:
        GEMINI_KEYS.append(key)

OPENROUTER_KEYS = []
for i in range(1, 10):
    key = os.environ.get(f"OPENROUTER_KEY{i}")
    if key:
        OPENROUTER_KEYS.append(key)

# حالة المفاتيح
key_states = {
    'deepseek': {'keys': DEEPSEEK_KEYS, 'current_index': 0, 'failed_keys': set(), 'last_used': 0},
    'gemini': {'keys': GEMINI_KEYS, 'current_index': 0, 'failed_keys': set(), 'last_used': 0},
    'openrouter': {'keys': OPENROUTER_KEYS, 'current_index': 0, 'failed_keys': set(), 'last_used': 0}
}

# إعدادات المحاولات
MAX_RETRIES_POLLINATIONS = 5  # 5 محاولات لـ Pollinations
RETRY_DELAY_SECONDS = 60      # انتظار دقيقة بين المحاولات
MAX_RETRIES_BACKUP_IMAGE = 3

# ========== مواقع توليد الصور ==========
async def image_pollinations(prompt: str, seed: int):
    """Pollinations API - سيتم إعادة المحاولة بعد دقيقة إذا فشل"""
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
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
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

async def image_local_fallback(prompt: str, update: Update):
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
        
        draw.text((50, y+20), "~ صورة احتياطية ~", fill=(200, 200, 200), font=font)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "fallback_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 **صورة احتياطية (محلية)**\n\n📝 {prompt[:150]}..."
        )
        return True
    except:
        return False

# ========== وظيفة توليد الصور مع إعادة المحاولة بعد دقيقة ==========
async def generate_image_with_retry(prompt: str, update: Update, user_id: int):
    """توليد صورة مع إعادة المحاولة بعد دقيقة إذا فشل البوت"""
    
    # إرسال رسالة المعالجة
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة...**\n\n"
        f"📝 {prompt[:150]}\n\n"
        f"⏳ سيتم المحاولة {MAX_RETRIES_POLLINATIONS} مرة\n"
        f"⏱ انتظار {RETRY_DELAY_SECONDS} ثانية بين المحاولات"
    )
    
    image_data = None
    success = False
    
    # المحاولات المتعددة لـ Pollinations
    for attempt in range(MAX_RETRIES_POLLINATIONS):
        if success:
            break
            
        await processing_msg.edit_text(
            f"🎨 **Pollinations - المحاولة {attempt + 1}/{MAX_RETRIES_POLLINATIONS}**\n\n"
            f"📝 {prompt[:100]}...\n\n"
            f"⏳ جاري التوليد..."
        )
        
        # محاولة توليد الصورة
        try:
            random_seed = random.randint(1, 1000000) + attempt * 1000
            image_data = await image_pollinations(prompt, random_seed)
            
            if image_data:
                success = True
                break
        except Exception as e:
            logger.error(f"محاولة {attempt + 1} فشلت: {e}")
        
        if attempt < MAX_RETRIES_POLLINATIONS - 1:
            await processing_msg.edit_text(
                f"⚠️ **المحاولة {attempt + 1} فشلت**\n\n"
                f"⏳ انتظار {RETRY_DELAY_SECONDS} ثانية قبل المحاولة التالية...\n"
                f"🔄 سيتم إعادة المحاولة تلقائياً"
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    
    # إذا فشل Pollinations، جرب البدائل
    if not success:
        await processing_msg.edit_text("⚠️ **Pollinations غير متاح، أجرب مواقع بديلة...**")
        
        # Craiyon
        await processing_msg.edit_text("🖼 **جاري تجربة Craiyon...**")
        image_data = await image_craiyon(prompt)
        if image_data:
            success = True
        
        # Lexica
        if not success:
            await processing_msg.edit_text("🖼 **جاري تجربة Lexica...**")
            image_data = await image_lexica(prompt)
            if image_data:
                success = True
        
        # DeepAI
        if not success:
            await processing_msg.edit_text("🖼 **جاري تجربة DeepAI...**")
            image_data = await image_deepai(prompt)
            if image_data:
                success = True
    
    await processing_msg.delete()
    
    if success and image_data:
        image_file = io.BytesIO(image_data)
        image_file.name = "generated_image.png"
        await update.message.reply_photo(
            photo=image_file,
            caption=f"🎨 **تم توليد الصورة بنجاح!**\n\n📝 {prompt[:150]}..."
        )
        await update.message.reply_text("✅ تم توليد الصورة بنجاح!")
        return True
    else:
        # الرسم المحلي (الحل الأخير)
        return await image_local_fallback(prompt, update)

# ========== تقسيم النص الطويل وتوليد صور متعددة ==========
async def generate_images_for_long_text(text: str, update: Update, user_id: int):
    """تقسيم النص الطويل إلى أجزاء وتوليد صورة لكل جزء"""
    
    # تقسيم النص إلى أجزاء
    lines = text.split('\n')
    sentences = re.split(r'[.!?؟]\s+', text)
    
    # إذا كان النص طويلاً (أكثر من 3 جمل أو 5 أسطر)
    if len(sentences) > 3 or len(lines) > 5 or len(text) > 300:
        # تقسيم إلى أجزاء
        parts = []
        
        if len(sentences) > 3:
            # تقسيم حسب الجمل
            chunk_size = max(2, len(sentences) // 3)
            for i in range(0, len(sentences), chunk_size):
                part = ' '.join(sentences[i:i+chunk_size])
                if part.strip():
                    parts.append(part.strip())
        else:
            # تقسيم حسب السطور
            chunk_size = max(2, len(lines) // 3)
            for i in range(0, len(lines), chunk_size):
                part = '\n'.join(lines[i:i+chunk_size])
                if part.strip():
                    parts.append(part.strip())
        
        # إذا كان عدد الأجزاء قليلاً، اجعل 3 أجزاء كحد أقصى
        parts = parts[:3]
        
        # إعلام المستخدم
        await update.message.reply_text(
            f"📝 **نص طويل!** سأقوم بتقسيمه إلى {len(parts)} أجزاء\n"
            f"🖼 سأقوم بتوليد صورة لكل جزء"
        )
        
        # توليد صورة لكل جزء
        for idx, part in enumerate(parts, 1):
            await update.message.reply_text(f"🎨 **جاري توليد الصورة {idx}/{len(parts)}...**")
            await generate_image_with_retry(part, update, user_id)
            await asyncio.sleep(2)  # انتظار قليل بين الصور
        
        return True
    else:
        # نص قصير، صورة واحدة فقط
        return await generate_image_with_retry(text, update, user_id)

# ========== شرح النص باستخدام المفاتيح مع إعادة التدوير ==========

async def call_deepseek_with_retry(prompt: str, update: Update, processing_msg):
    """DeepSeek مع إعادة تدوير المفاتيح"""
    keys_list = key_states['deepseek']['keys']
    
    if not keys_list:
        return False
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['deepseek']['failed_keys']:
            continue
        
        await processing_msg.edit_text(f"📖 **DeepSeek - مفتاح {key_idx + 1}/{len(keys_list)}**")
        
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
                        key_states['deepseek']['failed_keys'].add(key_idx)
                        logger.warning(f"DeepSeek key {key_idx + 1} فشل مع status {resp.status}")
        except Exception as e:
            key_states['deepseek']['failed_keys'].add(key_idx)
            logger.error(f"DeepSeek key {key_idx + 1} error: {e}")
    
    return False

async def call_gemini_with_retry(prompt: str, update: Update, processing_msg):
    """Gemini مع إعادة تدوير المفاتيح"""
    keys_list = key_states['gemini']['keys']
    
    if not keys_list:
        return False
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['gemini']['failed_keys']:
            continue
        
        await processing_msg.edit_text(f"📖 **Gemini - مفتاح {key_idx + 1}/{len(keys_list)}**")
        
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
                        key_states['gemini']['failed_keys'].add(key_idx)
                        logger.warning(f"Gemini key {key_idx + 1} فشل")
        except Exception as e:
            key_states['gemini']['failed_keys'].add(key_idx)
            logger.error(f"Gemini key {key_idx + 1} error: {e}")
    
    return False

async def call_openrouter_with_retry(prompt: str, update: Update, processing_msg):
    """OpenRouter مع إعادة تدوير المفاتيح"""
    keys_list = key_states['openrouter']['keys']
    
    if not keys_list:
        return False
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['openrouter']['failed_keys']:
            continue
        
        await processing_msg.edit_text(f"📖 **OpenRouter - مفتاح {key_idx + 1}/{len(keys_list)}**")
        
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
                        key_states['openrouter']['failed_keys'].add(key_idx)
                        logger.warning(f"OpenRouter key {key_idx + 1} فشل")
        except Exception as e:
            key_states['openrouter']['failed_keys'].add(key_idx)
            logger.error(f"OpenRouter key {key_idx + 1} error: {e}")
    
    return False

# شرح محلي (البديل النهائي)
async def explain_local_advanced(text: str, update: Update):
    """شرح متقدم محلياً (يعمل دائماً)"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    word_lengths = [len(w) for w in words]
    avg_word_length = sum(word_lengths) / len(word_lengths) if words else 0
    
    word_freq = {}
    for word in words:
        word_lower = word.lower()
        word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
    
    most_common = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    
    explanation = f"""
📚 **تحليل وشرح النص (متقدم محلي)**

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
🌐 **اللغة المكتشفة:** {'عربية' if has_arabic else 'إنجليزية/أخرى'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔝 **الكلمات الأكثر تكراراً:**
"""
    for word, count in most_common:
        explanation += f"• '{word}': {count} مرة\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 **تقييم النص:**
• الطول: {'قصير' if len(words) < 20 else 'متوسط' if len(words) < 50 else 'طويل'}

💡 **ملخص النص:**
{text[:200]}{'...' if len(text) > 200 else ''}

✅ **تم التحليل والشرح بنجاح**
"""
    await update.message.reply_text(explanation)
    return True

async def explain_text_full(text: str, update: Update):
    """شرح النص باستخدام المفاتيح مع إعادة التدوير"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    # الأولوية: DeepSeek
    if DEEPSEEK_KEYS and not success:
        success = await call_deepseek_with_retry(text, update, processing_msg)
    
    # الثاني: Gemini
    if GEMINI_KEYS and not success:
        success = await call_gemini_with_retry(text, update, processing_msg)
    
    # الثالث: OpenRouter
    if OPENROUTER_KEYS and not success:
        success = await call_openrouter_with_retry(text, update, processing_msg)
    
    # الرابع: شرح محلي (يعمل دائماً)
    if not success:
        await processing_msg.edit_text("📖 **جميع الخدمات غير متاحة، جاري التحليل المحلي...**")
        success = await explain_local_advanced(text, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحليل وشرح النص بنجاح!")

# ========== تحويل النص إلى صوت ==========
async def google_tts_with_retry(text: str, lang: str, gender: str, update: Update, processing_msg):
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
    return False

async def generate_audio(text: str, gender: str, update: Update):
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    lang = 'ar' if has_arabic else 'en'
    
    processing_msg = await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت...**")
    
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
        f"   • {MAX_RETRIES_POLLINATIONS} محاولات لـ Pollinations\n"
        f"   • انتظار {RETRY_DELAY_SECONDS} ثانية بين المحاولات\n"
        f"   • تقسيم النصوص الطويلة إلى صور متعددة\n\n"
        f"🎵 **تحويل نص إلى صوت:** 3 محاولات\n\n"
        f"📖 **شرح وتحليل النص:**\n"
        f"   • DeepSeek, Gemini, OpenRouter مع إعادة تدوير المفاتيح\n"
        f"   • مفاتيح متاحة: DeepSeek({len(DEEPSEEK_KEYS)}), Gemini({len(GEMINI_KEYS)}), OpenRouter({len(OPENROUTER_KEYS)})\n"
        f"   • بديل محلي يعمل دائماً\n\n"
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
            f"✅ {MAX_RETRIES_POLLINATIONS} محاولات لـ Pollinations\n"
            f"✅ انتظار {RETRY_DELAY_SECONDS} ثانية بين المحاولات\n"
            f"✅ النصوص الطويلة تقسم إلى صور متعددة\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة مع زهور\n"
            "• قطة نائمة على كنبة"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            f"✅ DeepSeek: {len(DEEPSEEK_KEYS)} مفتاح\n"
            f"✅ Gemini: {len(GEMINI_KEYS)} مفتاح\n"
            f"✅ OpenRouter: {len(OPENROUTER_KEYS)} مفتاح\n"
            f"✅ بديل محلي يعمل دائماً"
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
    user_id = update.effective_user.id
    user_text = update.message.text
    
    await generate_images_for_long_text(user_text, update, user_id)
    
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

# ========== إعادة التشغيل التلقائي ==========
def restart_bot():
    """إعادة تشغيل البوت تلقائياً"""
    logger.warning("⚠️ جاري إعادة تشغيل البوت...")
    time.sleep(2)
    os.execl(sys.executable, sys.executable, *sys.argv)

def signal_handler(signum, frame):
    """معالج إشارات لإعادة التشغيل"""
    logger.warning(f"⚠️ استقبل إشارة {signum}، جاري إعادة التشغيل...")
    restart_bot()

# ========== التشغيل ==========
def main():
    # تسجيل معالج الإشارات لإعادة التشغيل التلقائي
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
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
    print("✅ البوت يعمل مع نظام إعادة التشغيل التلقائي!")
    print(f"📊 Pollinations: {MAX_RETRIES_POLLINATIONS} محاولات")
    print(f"📊 انتظار {RETRY_DELAY_SECONDS} ثانية بين المحاولات")
    print(f"📊 تقسيم النصوص الطويلة إلى صور متعددة")
    print(f"📊 DeepSeek Keys: {len(DEEPSEEK_KEYS)}")
    print(f"📊 Gemini Keys: {len(GEMINI_KEYS)}")
    print(f"📊 OpenRouter Keys: {len(OPENROUTER_KEYS)}")
    print("=" * 60)
    
    try:
        app.run_polling()
    except Exception as e:
        logger.error(f"⚠️ البوت توقف: {e}")
        logger.warning("🔄 جاري إعادة التشغيل التلقائي بعد 5 ثوان...")
        time.sleep(5)
        restart_bot()

if __name__ == "__main__":
    main()
