import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE = range(4)

# تخزين بيانات المستخدمين
user_choices = {}

# ========== بدائل توليد الصور من النص (مجانية 100%) ==========

# البديل 1: Pollinations API (أفضل بديل مجاني)
async def generate_image_pollinations(prompt: str, update: Update):
    """توليد صورة من النص باستخدام Pollinations API - مجاني"""
    try:
        # تنظيف النص وإضافة كلمات كرتونية
        clean_prompt = prompt.strip().replace(" ", "%20")
        # إضافة أسلوب كرتوني للحصول على صور كرتونية
        cartoon_prompt = f"{clean_prompt}, cartoon style, colorful, cute illustration"
        encoded_prompt = urllib.parse.quote(cartoon_prompt)
        
        # استخدام Pollinations API (مجاني، لا يحتاج مفتاح)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={random.randint(1, 10000)}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=25) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "generated_image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🖼 **تم توليد الصورة بنجاح**\n\n📝 **الوصف:** {prompt[:150]}...\n\n🎨 **المصدر:** Pollinations AI"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
        return False

# البديل 2: Lexica API (مجاني، يبحث عن صور مشابهة)
async def generate_image_lexica(prompt: str, update: Update):
    """توليد صورة باستخدام Lexica API - مجاني"""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://lexica.art/api/v1/search?q={encoded_prompt}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        # أخذ أول صورة
                        image_url = images[0].get('src')
                        if image_url:
                            async with session.get(image_url) as img_resp:
                                image_data = await img_resp.read()
                                if len(image_data) > 1000:
                                    image_file = io.BytesIO(image_data)
                                    image_file.name = "lexica_image.png"
                                    await update.message.reply_photo(
                                        photo=image_file,
                                        caption=f"🖼 **تم توليد الصورة بنجاح**\n\n📝 **الوصف:** {prompt[:150]}...\n\n🎨 **المصدر:** Lexica AI"
                                    )
                                    return True
        return False
    except Exception as e:
        logger.error(f"Lexica error: {e}")
        return False

# البديل 3: Craiyon API (مجاني، مشهور)
async def generate_image_craiyon(prompt: str, update: Update):
    """توليد صورة باستخدام Craiyon API - مجاني"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backend.craiyon.com/generate",
                json={"prompt": f"cartoon style, {prompt}"},
                timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get('images', [])
                    if images and len(images) > 0:
                        image_data = base64.b64decode(images[0])
                        if len(image_data) > 1000:
                            image_file = io.BytesIO(image_data)
                            image_file.name = "craiyon_image.png"
                            await update.message.reply_photo(
                                photo=image_file,
                                caption=f"🖼 **تم توليد الصورة بنجاح**\n\n📝 **الوصف:** {prompt[:150]}...\n\n🎨 **المصدر:** Craiyon AI"
                            )
                            return True
        return False
    except Exception as e:
        logger.error(f"Craiyon error: {e}")
        return False

# البديل 4: Hugging Face API (مجاني مع نماذج مفتوحة المصدر)
async def generate_image_huggingface(prompt: str, update: Update):
    """توليد صورة باستخدام Hugging Face API - مجاني"""
    try:
        # استخدام نموذج مجاني من Hugging Face
        API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
        
        # يمكنك الحصول على مفتاح مجاني من huggingface.co
        HF_TOKEN = os.environ.get("HF_TOKEN", "")
        
        if not HF_TOKEN:
            return False
        
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": f"cartoon style, colorful, {prompt}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    if len(image_data) > 1000:
                        image_file = io.BytesIO(image_data)
                        image_file.name = "hf_image.png"
                        await update.message.reply_photo(
                            photo=image_file,
                            caption=f"🖼 **تم توليد الصورة بنجاح**\n\n📝 **الوصف:** {prompt[:150]}...\n\n🎨 **المصدر:** Hugging Face"
                        )
                        return True
        return False
    except Exception as e:
        logger.error(f"HuggingFace error: {e}")
        return False

# البديل 5: OpenAI DALL-E مجاني عبر Proxy
async def generate_image_dalle_proxy(prompt: str, update: Update):
    """توليد صورة باستخدام DALL-E Proxy مجاني"""
    try:
        encoded_prompt = urllib.parse.quote(f"cartoon illustration, {prompt}")
        url = f"https://tiny-img.com/api/generate?prompt={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "dalle_image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🖼 **تم توليد الصورة بنجاح**\n\n📝 **الوصف:** {prompt[:150]}...\n\n🎨 **المصدر:** DALL-E Proxy"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"DALL-E Proxy error: {e}")
        return False

# الوظيفة الرئيسية لتوليد الصور (تجربة جميع البدائل)
async def generate_image_from_text(prompt: str, update: Update):
    """توليد صورة من النص باستخدام جميع البدائل المتاحة"""
    
    # إرسال رسالة المعالجة
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة من النص...**\n\n"
        f"📝 **الوصف:** {prompt[:200]}\n\n"
        f"🔄 **أجرب جميع البدائل المجانية:**"
    )
    
    await asyncio.sleep(0.5)
    
    success = False
    
    # البديل 1: Pollinations
    await processing_msg.edit_text(f"🖼 **البديل 1/5:** Pollinations AI\n📝 {prompt[:100]}...")
    success = await generate_image_pollinations(prompt, update)
    
    # البديل 2: Lexica
    if not success:
        await processing_msg.edit_text(f"🖼 **البديل 2/5:** Lexica AI\n📝 {prompt[:100]}...")
        success = await generate_image_lexica(prompt, update)
    
    # البديل 3: Craiyon
    if not success:
        await processing_msg.edit_text(f"🖼 **البديل 3/5:** Craiyon AI\n📝 {prompt[:100]}...")
        success = await generate_image_craiyon(prompt, update)
    
    # البديل 4: Hugging Face
    if not success:
        await processing_msg.edit_text(f"🖼 **البديل 4/5:** Hugging Face\n📝 {prompt[:100]}...")
        success = await generate_image_huggingface(prompt, update)
    
    # البديل 5: DALL-E Proxy
    if not success:
        await processing_msg.edit_text(f"🖼 **البديل 5/5:** DALL-E Proxy\n📝 {prompt[:100]}...")
        success = await generate_image_dalle_proxy(prompt, update)
    
    await processing_msg.delete()
    
    if not success:
        await update.message.reply_text(
            "❌ **عذراً، جميع خدمات توليد الصور غير متاحة حالياً.**\n\n"
            "💡 **نصائح للحصول على صورة:**\n"
            "• استخدم وصفاً باللغة الإنجليزية\n"
            "• مثال: 'a boy playing in a garden'\n"
            "• مثال: 'cute cat sleeping on a sofa'\n"
            "• مثال: 'beautiful sunset over mountains'\n\n"
            "🔄 **يرجى المحاولة مرة أخرى بنص مختلف.**"
        )

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
    
    processing_msg = await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت {'(ذكر)' if gender=='male' else '(أنثى)'}...**")
    
    success = await google_tts(text, lang, gender, update)
    
    await processing_msg.delete()
    
    if success:
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً. حاول بنص أقصر.")

# ========== تحليل النص وشرحه ==========
async def explain_text(text: str, update: Update):
    words = text.split()
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    explanation = f"""
📚 **شرح وتحليل النص**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:300]}{'...' if len(text) > 300 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {text.count('.') + text.count('!') + text.count('?') + text.count('؟')}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━
📏 **الطول:** {'قصير' if len(words) < 15 else 'متوسط' if len(words) < 40 else 'طويل'}

✅ **تم التحليل بنجاح**
"""
    await update.message.reply_text(explanation)

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة من النص", callback_data="action_image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="action_audio")],
        [InlineKeyboardButton("📖 شرح وتحليل النص", callback_data="action_explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة من النص:**\n"
        "اكتب أي وصف وسأقوم بتوليد صورة كرتونية له\n"
        "مثال: 'ولد في حديقة مع زهور'\n"
        "مثال: 'قطة نائمة على كنبة'\n\n"
        "🎵 **تحويل نص إلى صوت:**\n"
        "يحول أي نص إلى ملف MP3 (اختيار ذكر/أنثى)\n\n"
        "📖 **شرح وتحليل النص:**\n"
        "يحلل النص ويعطيك إحصائيات عنه\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
            "🎨 **توليد صورة من النص**\n\n"
            "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
            "📝 **أمثلة:**\n"
            "• a boy playing in a garden\n"
            "• a cute cat sleeping on a sofa\n"
            "• ولد في حديقة مع زهور\n"
            "• غابة مع حيوانات كرتونية\n\n"
            "✅ سأقوم بتوليد صورة حسب وصفك"
        )
        return WAITING_FOR_TEXT_IMAGE
        
    elif action == "action_explain":
        await query.edit_message_text(
            "📖 **شرح وتحليل النص**\n\n"
            "✏️ **أرسل النص الذي تريد تحليله:**\n\n"
            "✅ سأقوم بتحليل النص وإعطائك:\n"
            "• عدد الحروف والكلمات\n"
            "• اللغة المكتشفة\n"
            "• طول النص"
        )
        return WAITING_FOR_TEXT_IMAGE  # سنستخدم نفس الحالة
        
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
    
    # معرفة إذا كان المستخدم يريد شرحاً أم صورة
    # هذا يعتمد على آخر زر ضغط عليه
    
    # بشكل افتراضي، نعتبر أنها صورة
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء. استخدم /start للبدء.")
    return ConversationHandler.END

# ========== التشغيل ==========
def main():
    import random
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern="^(action_audio|action_image|action_explain|back_to_start)$")],
            CHOOSING_AUDIO_GENDER: [CallbackQueryHandler(audio_gender_choice, pattern="^(audio_male|audio_female|back_to_start)$")],
            WAITING_FOR_TEXT_AUDIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_audio_text)],
            WAITING_FOR_TEXT_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_image_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل - توليد صور من النص باستخدام 5 بدائل مجانية")
    app.run_polling()

if __name__ == "__main__":
    main()
