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
# DeepSeek Keys
DEEPSEEK_KEYS = []
for i in range(1, 10):  # deepseek_key1 إلى deepseek_key9
    key = os.environ.get(f"DEEPSEEK_KEY{i}")
    if key:
        DEEPSEEK_KEYS.append(key)

# Gemini Keys
GEMINI_KEYS = []
for i in range(1, 10):  # gemini_key1 إلى gemini_key9
    key = os.environ.get(f"GEMINI_KEY{i}")
    if key:
        GEMINI_KEYS.append(key)

# OpenRouter Keys
OPENROUTER_KEYS = []
for i in range(1, 10):  # openrouter_key1 إلى openrouter_key9
    key = os.environ.get(f"OPENROUTER_KEY{i}")
    if key:
        OPENROUTER_KEYS.append(key)

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE, WAITING_FOR_EXPLAIN = range(5)

# تخزين بيانات المستخدمين
user_choices = {}

# تخزين حالة المفاتيح (أي مفتاح يستخدم حالياً)
key_states = {
    'deepseek': {'keys': DEEPSEEK_KEYS, 'current_index': 0, 'failed_keys': set()},
    'gemini': {'keys': GEMINI_KEYS, 'current_index': 0, 'failed_keys': set()},
    'openrouter': {'keys': OPENROUTER_KEYS, 'current_index': 0, 'failed_keys': set()}
}

# ========== بدائل توليد الصور (Pollinations أولاً) ==========

# البديل 1: Pollinations (الأفضل - أولوية أولى)
async def image_pollinations(prompt: str, update: Update):
    """توليد صورة باستخدام Pollinations - يعمل دائماً"""
    try:
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful, high quality")
        # إضافة seed عشوائي للحصول على صور مختلفة
        random_seed = random.randint(1, 100000)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={random_seed}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "pollinations.png"
            await update.message.reply_photo(
                photo=image_file, 
                caption=f"🎨 **صورة من Pollinations AI**\n\n📝 **الوصف:** {prompt[:150]}...\n\n✅ تم التوليد بنجاح!"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
        return False

# بديل احتياطي 1: Craiyon
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
                        await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Craiyon (بديل)\n📝 {prompt[:100]}")
                        return True
        return False
    except:
        return False

# بديل احتياطي 2: Lexica
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
                                    await update.message.reply_photo(photo=image_file, caption=f"🎨 صورة من Lexica (بديل)\n📝 {prompt[:100]}")
                                    return True
        return False
    except:
        return False

# بديل احتياطي 3: رسم محلي
async def image_local_fallback(prompt: str, update: Update):
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
        
        draw.text((50, y+20), "~ Pollinations غير متاح حالياً ~", fill=(200, 200, 200), font=font)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_buffer.name = "fallback_image.png"
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 **صورة احتياطية (محلية)**\n\n📝 {prompt[:150]}...\n\n⚠️ Pollinations غير متاح حالياً، جرب مرة أخرى."
        )
        return True
    except:
        return False

# ========== شرح النص باستخدام مفاتيح API (DeepSeek ← Gemini ← OpenRouter) ==========

async def call_deepseek(prompt: str, update: Update):
    """استدعاء DeepSeek API"""
    keys_list = key_states['deepseek']['keys']
    current_idx = key_states['deepseek']['current_index']
    failed_keys = key_states['deepseek']['failed_keys']
    
    for i in range(len(keys_list)):
        idx = (current_idx + i) % len(keys_list)
        if idx in failed_keys:
            continue
        
        api_key = keys_list[idx]
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "أنت مساعد ذكي متخصص في تحليل وشرح النصوص. قم بتحليل النص التالي وشرحه بشكل مفصل."},
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
                        # هذا المفتاح فشل
                        failed_keys.add(idx)
                        logger.warning(f"DeepSeek key {idx+1} failed with status {resp.status}")
                        continue
        except Exception as e:
            failed_keys.add(idx)
            logger.error(f"DeepSeek key {idx+1} error: {e}")
            continue
    
    return False

async def call_gemini(prompt: str, update: Update):
    """استدعاء Gemini API"""
    keys_list = key_states['gemini']['keys']
    current_idx = key_states['gemini']['current_index']
    failed_keys = key_states['gemini']['failed_keys']
    
    for i in range(len(keys_list)):
        idx = (current_idx + i) % len(keys_list)
        if idx in failed_keys:
            continue
        
        api_key = keys_list[idx]
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
                        failed_keys.add(idx)
                        continue
        except Exception as e:
            failed_keys.add(idx)
            continue
    
    return False

async def call_openrouter(prompt: str, update: Update):
    """استدعاء OpenRouter API"""
    keys_list = key_states['openrouter']['keys']
    current_idx = key_states['openrouter']['current_index']
    failed_keys = key_states['openrouter']['failed_keys']
    
    for i in range(len(keys_list)):
        idx = (current_idx + i) % len(keys_list)
        if idx in failed_keys:
            continue
        
        api_key = keys_list[idx]
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
                        failed_keys.add(idx)
                        continue
        except Exception as e:
            failed_keys.add(idx)
            continue
    
    return False

# شرح النص المحلي (البديل النهائي)
async def explain_local_fallback(text: str, update: Update):
    """شرح محلي إذا فشلت جميع APIs"""
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
    """شرح النص باستخدام المفاتيح بالترتيب"""
    
    processing_msg = await update.message.reply_text("📖 **جاري تحليل وشرح النص...**")
    
    success = False
    
    # الأولوية: DeepSeek
    if DEEPSEEK_KEYS and not success:
        await processing_msg.edit_text("📖 **جاري الاتصال بـ DeepSeek AI...**")
        success = await call_deepseek(text, update)
    
    # الثاني: Gemini
    if GEMINI_KEYS and not success:
        await processing_msg.edit_text("📖 **جاري الاتصال بـ Gemini AI...**")
        success = await call_gemini(text, update)
    
    # الثالث: OpenRouter
    if OPENROUTER_KEYS and not success:
        await processing_msg.edit_text("📖 **جاري الاتصال بـ OpenRouter AI...**")
        success = await call_openrouter(text, update)
    
    # الأخير: شرح محلي
    if not success:
        await processing_msg.edit_text("📖 **جميع الخدمات غير متاحة، جاري التحليل المحلي...**")
        success = await explain_local_fallback(text, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحليل وشرح النص بنجاح!")

# ========== الوظيفة الرئيسية لتوليد الصور ==========
async def generate_image_from_text(prompt: str, update: Update):
    """توليد صورة باستخدام Pollinations أولاً، ثم بدائل"""
    
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة...**\n\n"
        f"📝 {prompt[:150]}\n\n"
        f"🔄 **جاري الاتصال بـ Pollinations...**"
    )
    
    success = False
    
    # الأولوية الأولى: Pollinations (الأفضل)
    success = await image_pollinations(prompt, update)
    
    # إذا فشل Pollinations، جرب البدائل
    if not success:
        await processing_msg.edit_text("⚠️ **Pollinations غير متاح حالياً، أجرب بدائل احتياطية...**")
        
        # بديل 1: Craiyon
        await processing_msg.edit_text("🖼 **البديل 1/3:** Craiyon...")
        success = await image_craiyon(prompt, update)
        
        # بديل 2: Lexica
        if not success:
            await processing_msg.edit_text("🖼 **البديل 2/3:** Lexica...")
            success = await image_lexica(prompt, update)
        
        # بديل 3: رسم محلي
        if not success:
            await processing_msg.edit_text("🖼 **البديل 3/3:** رسم محلي...")
            success = await image_local_fallback(prompt, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم توليد الصورة بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، جميع خدمات الصور غير متاحة. حاول مرة أخرى.")

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

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة من النص", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح وتحليل النص", callback_data="action_explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة:**\n"
        "   • الأولوية: Pollinations (أفضل خدمة مجانية)\n"
        "   • بدائل احتياطية: Craiyon, Lexica, رسم محلي\n\n"
        "🎵 **تحويل نص إلى صوت:**\n"
        "   • تحويل أي نص إلى MP3\n"
        "   • اختيار ذكر أو أنثى\n\n"
        "📖 **شرح وتحليل النص:**\n"
        "   • الأولوية: DeepSeek AI\n"
        "   • الثاني: Gemini AI\n"
        "   • الثالث: OpenRouter AI\n"
        f"   • مفاتيح متاحة: DeepSeek({len(DEEPSEEK_KEYS)}), Gemini({len(GEMINI_KEYS)}), OpenRouter({len(OPENROUTER_KEYS)})\n\n"
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
            "✅ الأولوية لـ Pollinations (أفضل خدمة مجانية)"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            "✅ الأولوية: DeepSeek AI\n"
            "✅ الثاني: Gemini AI\n"
            "✅ الثالث: OpenRouter AI\n"
            "✅ بديل احتياطي: تحليل محلي\n\n"
            f"📊 المفاتيح المتاحة: DeepSeek({len(DEEPSEEK_KEYS)}), Gemini({len(GEMINI_KEYS)}), OpenRouter({len(OPENROUTER_KEYS)})"
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
    
    print("=" * 50)
    print("✅ البوت يعمل!")
    print(f"📊 DeepSeek Keys: {len(DEEPSEEK_KEYS)}")
    print(f"📊 Gemini Keys: {len(GEMINI_KEYS)}")
    print(f"📊 OpenRouter Keys: {len(OPENROUTER_KEYS)}")
    print("🎨 Pollinations: الأولوية الأولى للصور")
    print("=" * 50)
    app.run_polling()

if __name__ == "__main__":
    main()
