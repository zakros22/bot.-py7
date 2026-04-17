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
import time
import signal
import subprocess
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME")
HEROKU_API_KEY = os.environ.get("HEROKU_API_KEY")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE, WAITING_FOR_EXPLAIN = range(5)

# تخزين بيانات المستخدمين
user_choices = {}
user_pending_requests = {}

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
    'deepseek': {'keys': DEEPSEEK_KEYS, 'current_index': 0, 'failed_keys': set()},
    'gemini': {'keys': GEMINI_KEYS, 'current_index': 0, 'failed_keys': set()},
    'openrouter': {'keys': OPENROUTER_KEYS, 'current_index': 0, 'failed_keys': set()}
}

# ========== وظيفة إعادة تشغيل Heroku Dyno ==========
def restart_heroku_dyno():
    """إعادة تشغيل الـ Dyno على Heroku"""
    try:
        if HEROKU_APP_NAME:
            logger.info(f"🔄 جاري إعادة تشغيل Dyno: {HEROKU_APP_NAME}")
            
            # استخدام Heroku API
            if HEROKU_API_KEY:
                try:
                    import requests
                    headers = {
                        "Authorization": f"Bearer {HEROKU_API_KEY}",
                        "Accept": "application/vnd.heroku+json; version=3",
                        "Content-Type": "application/json"
                    }
                    url = f"https://api.heroku.com/apps/{HEROKU_APP_NAME}/dynos"
                    response = requests.delete(url, headers=headers)
                    if response.status_code in [200, 202]:
                        logger.info("✅ تم إعادة تشغيل الـ Dyno عبر API")
                        return True
                except:
                    pass
            
            # استخدام CLI
            try:
                result = subprocess.run(
                    ["heroku", "restart", "-a", HEROKU_APP_NAME],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    logger.info("✅ تم إعادة تشغيل الـ Dyno عبر CLI")
                    return True
            except:
                pass
            
            # استخدام Scale
            try:
                subprocess.run(
                    ["heroku", "ps:scale", "worker=0", "-a", HEROKU_APP_NAME],
                    capture_output=True, timeout=10
                )
                time.sleep(2)
                subprocess.run(
                    ["heroku", "ps:scale", "worker=1", "-a", HEROKU_APP_NAME],
                    capture_output=True, timeout=10
                )
                logger.info("✅ تم إعادة تشغيل الـ Dyno عبر Scale")
                return True
            except:
                pass
        
        return False
    except Exception as e:
        logger.error(f"خطأ في إعادة التشغيل: {e}")
        return False

# ========== صورة احتياطية محلية ==========
async def image_local_fallback(prompt: str, update: Update):
    """رسم صورة محلية"""
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
        await update.message.reply_text("❌ عذراً، جميع خدمات الصور غير متاحة. حاول مرة أخرى.")
        return False

# ========== وظيفة توليد الصورة مع إعادة تشغيل مسبق ==========
async def generate_image_with_prerestart(prompt: str, update: Update, user_id: int, attempt: int = 0):
    """توليد صورة مع إعادة تشغيل الـ Dyno قبل المحاولة"""
    
    MAX_ATTEMPTS = 3
    
    # إرسال رسالة للمستخدم
    if attempt == 0:
        await update.message.reply_text(
            f"🎨 **جاري تحضير النظام لتوليد الصورة...**\n\n"
            f"📝 {prompt[:150]}\n\n"
            f"🔄 سيتم إعادة تشغيل الخادم أولاً لضمان عمل أفضل\n"
            f"⏱ سيستغرق هذا 5-10 ثواني"
        )
    
    # إعادة تشغيل الـ Dyno قبل المحاولة
    await update.message.reply_text(f"🔄 **إعادة تشغيل الخادم... (المحاولة {attempt + 1}/{MAX_ATTEMPTS})**")
    
    restart_success = restart_heroku_dyno()
    
    if restart_success:
        await update.message.reply_text("✅ **تم إعادة تشغيل الخادم بنجاح!**\n\n🎨 جاري توليد الصورة...")
    else:
        await update.message.reply_text("⚠️ **جاري توليد الصورة بدون إعادة تشغيل...**")
    
    # انتظار قليل بعد إعادة التشغيل
    await asyncio.sleep(3)
    
    # محاولة توليد الصورة
    image_data = None
    success = False
    
    # محاولة Pollinations
    for retry in range(2):
        try:
            clean_prompt = prompt.strip().replace(" ", "%20")
            encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful, high quality")
            random_seed = random.randint(1, 1000000) + attempt * 10000
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={random_seed}"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
                if len(image_data) > 1000:
                    success = True
                    break
        except Exception as e:
            logger.error(f"Pollinations error: {e}")
            if retry == 0:
                await asyncio.sleep(2)
    
    if success and image_data:
        image_file = io.BytesIO(image_data)
        image_file.name = "generated_image.png"
        await update.message.reply_photo(
            photo=image_file,
            caption=f"🎨 **تم توليد الصورة بنجاح!**\n\n📝 {prompt[:150]}..."
        )
        await update.message.reply_text("✅ تم توليد الصورة بنجاح!")
        return True
    
    # إذا فشلت المحاولة ولم نصل للحد الأقصى
    if attempt + 1 < MAX_ATTEMPTS:
        await update.message.reply_text(
            f"⚠️ **المحاولة {attempt + 1} فشلت**\n\n"
            f"🔄 جاري إعادة التشغيل والمحاولة مرة أخرى..."
        )
        return await generate_image_with_prerestart(prompt, update, user_id, attempt + 1)
    
    # إذا فشلت كل المحاولات، جرب البدائل
    await update.message.reply_text("⚠️ **Pollinations غير متاح، أجرب مواقع بديلة...**")
    
    # بديل 1: Craiyon
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://backend.craiyon.com/generate", json={"prompt": f"cartoon, {prompt}"}, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        image_data = base64.b64decode(images[0])
                        success = True
    except:
        pass
    
    # بديل 2: Lexica
    if not success:
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
                                    success = True
        except:
            pass
    
    # بديل 3: DeepAI
    if not success:
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
                                image_data = await img_resp.read()
                                success = True
        except:
            pass
    
    if success and image_data:
        image_file = io.BytesIO(image_data)
        image_file.name = "backup_image.png"
        await update.message.reply_photo(
            photo=image_file,
            caption=f"🎨 **تم توليد الصورة من موقع بديل!**\n\n📝 {prompt[:150]}..."
        )
        return True
    
    # الحل الأخير: رسم صورة محلية
    return await image_local_fallback(prompt, update)

# ========== تقسيم النص الطويل ==========
async def generate_images_for_long_text(text: str, update: Update, user_id: int):
    """تقسيم النص الطويل إلى أجزاء"""
    
    sentences = re.split(r'[.!?؟]\s+', text)
    
    if len(sentences) > 3 or len(text) > 300:
        chunk_size = max(2, len(sentences) // 3)
        parts = []
        for i in range(0, len(sentences), chunk_size):
            part = ' '.join(sentences[i:i+chunk_size])
            if part.strip():
                parts.append(part.strip())
        
        parts = parts[:3]
        
        await update.message.reply_text(
            f"📝 **نص طويل!** سأقوم بتقسيمه إلى {len(parts)} أجزاء\n"
            f"🖼 سأقوم بتوليد صورة لكل جزء\n"
            f"🔄 سيتم إعادة تشغيل الخادم قبل كل صورة"
        )
        
        for idx, part in enumerate(parts, 1):
            await update.message.reply_text(f"🎨 **جاري توليد الصورة {idx}/{len(parts)}...**")
            await generate_image_with_prerestart(part, update, user_id, 0)
            await asyncio.sleep(3)
        
        return True
    else:
        return await generate_image_with_prerestart(text, update, user_id, 0)

# ========== شرح النص باستخدام المفاتيح ==========

async def call_deepseek(prompt: str, update: Update, processing_msg):
    keys_list = key_states['deepseek']['keys']
    
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
                    {"role": "system", "content": "أنت مساعد ذكي متخصص في تحليل وشرح النصوص."},
                    {"role": "user", "content": f"حلل واشرح هذا النص:\n\n{prompt}"}
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
        except:
            key_states['deepseek']['failed_keys'].add(key_idx)
    
    return False

async def call_gemini(prompt: str, update: Update, processing_msg):
    keys_list = key_states['gemini']['keys']
    
    for key_idx, api_key in enumerate(keys_list):
        if key_idx in key_states['gemini']['failed_keys']:
            continue
        
        await processing_msg.edit_text(f"📖 **Gemini - مفتاح {key_idx + 1}/{len(keys_list)}**")
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": f"حلل واشرح هذا النص:\n\n{prompt}"}]
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
        except:
            key_states['gemini']['failed_keys'].add(key_idx)
    
    return False

async def call_openrouter(prompt: str, update: Update, processing_msg):
    keys_list = key_states['openrouter']['keys']
    
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
                    {"role": "user", "content": f"حلل واشرح هذا النص:\n\n{prompt}"}
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
        except:
            key_states['openrouter']['failed_keys'].add(key_idx)
    
    return False

async def explain_local(text: str, update: Update):
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    explanation = f"""
📚 **تحليل وشرح النص**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:500]}{'...' if len(text) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

💡 **ملخص:**
{text[:200]}{'...' if len(text) > 200 else ''}

✅ تم التحليل بنجاح
"""
    await update.message.reply_text(explanation)
    return True

async def explain_text_full(text: str, update: Update):
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    if DEEPSEEK_KEYS and not success:
        success = await call_deepseek(text, update, processing_msg)
    
    if GEMINI_KEYS and not success:
        success = await call_gemini(text, update, processing_msg)
    
    if OPENROUTER_KEYS and not success:
        success = await call_openrouter(text, update, processing_msg)
    
    if not success:
        await processing_msg.edit_text("📖 **جاري التحليل المحلي...**")
        success = await explain_local(text, update)
    
    await processing_msg.delete()

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
    
    success = False
    for attempt in range(3):
        await processing_msg.edit_text(f"🎙 **تحويل الصوت - المحاولة {attempt + 1}/3**")
        success = await google_tts(text, lang, gender, update)
        if success:
            break
        await asyncio.sleep(1)
    
    await processing_msg.delete()
    
    if not success:
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً.")

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
        f"   • قبل كل صورة → إعادة تشغيل الخادم تلقائياً\n"
        f"   • 3 محاولات مع إعادة تشغيل قبل كل محاولة\n"
        f"   • النصوص الطويلة تقسم إلى صور متعددة\n\n"
        f"🎵 **تحويل نص إلى صوت:** 3 محاولات\n\n"
        f"📖 **شرح وتحليل النص:**\n"
        f"   • DeepSeek ({len(DEEPSEEK_KEYS)} مفتاح)\n"
        f"   • Gemini ({len(GEMINI_KEYS)} مفتاح)\n"
        f"   • OpenRouter ({len(OPENROUTER_KEYS)} مفتاح)\n\n"
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
            f"✅ قبل كل صورة → إعادة تشغيل الخادم تلقائياً\n"
            f"✅ 3 محاولات مع إعادة تشغيل قبل كل محاولة\n"
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
            f"✅ OpenRouter: {len(OPENROUTER_KEYS)} مفتاح"
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
    print("✅ البوت يعمل مع إعادة تشغيل تلقائي قبل كل صورة!")
    print(f"📊 قبل كل صورة → إعادة تشغيل الـ Dyno")
    print(f"📊 3 محاولات مع إعادة تشغيل قبل كل محاولة")
    print(f"📊 DeepSeek Keys: {len(DEEPSEEK_KEYS)}")
    print(f"📊 Gemini Keys: {len(GEMINI_KEYS)}")
    print(f"📊 OpenRouter Keys: {len(OPENROUTER_KEYS)}")
    print("=" * 60)
    
    try:
        app.run_polling()
    except Exception as e:
        logger.error(f"⚠️ البوت توقف: {e}")
        logger.warning("🔄 جاري إعادة التشغيل التلقائي...")
        time.sleep(3)
        restart_bot()

if __name__ == "__main__":
    main()
