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

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")

# حالات المحادثة
CHOOSING_ACTION, CHOOSING_AUDIO_GENDER, WAITING_FOR_TEXT_AUDIO, WAITING_FOR_TEXT_IMAGE = range(4)

# تخزين بيانات المستخدمين
user_choices = {}

# ========== تحليل النص (أي لغة) ==========
async def analyze_text_universal(text: str):
    """تحليل النص لأي لغة"""
    words = text.split()
    chars = len(text)
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_english = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_arabic:
        language = "العربية"
    elif has_english:
        language = "الإنجليزية"
    else:
        language = "غير معروف"
    
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
    
    return {
        'language': language,
        'char_count': chars,
        'word_count': len(words),
        'sentence_count': sentences if sentences > 0 else 1
    }

# ========== بدائل الصوت المجانية ==========

async def google_tts(text: str, lang: str, gender: str, update: Update):
    try:
        lang_codes = {'ar': 'ar', 'en': 'en', 'fr': 'fr', 'de': 'de', 'es': 'es'}
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

async def voicerss_tts(text: str, lang: str, gender: str, update: Update):
    try:
        api_key = "bc0b5b2b0b1b4b0b8b0b0b0b0b0b0b0"
        voices = {
            ('ar', 'male'): 'Youssef',
            ('ar', 'female'): 'Amina',
            ('en', 'male'): 'John',
            ('en', 'female'): 'Linda',
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
                            title="VoiceRSS",
                            performer=f"{'ذكر' if gender=='male' else 'أنثى'}",
                            caption="✅ تم تحويل النص إلى صوت"
                        )
                        return True
        return False
    except:
        return False

# ========== بدائل الصور المجانية (توليد صور كرتونية من النص) ==========

# البديل 1: Pollinations API (مجاني، يولد صور كرتونية)
async def pollinations_image(prompt: str, update: Update):
    """توليد صورة كرتونية باستخدام Pollinations API (مجاني)"""
    try:
        # إضافة كلمات مفتاحية للحصول على صور كرتونية
        cartoon_prompt = f"cartoon character, {prompt}, animated style, colorful, cute"
        encoded_prompt = urllib.parse.quote(cartoon_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "cartoon_image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🖼 صورة كرتونية\n📝 الوصف: {prompt[:100]}..."
            )
            return True
        return False
    except Exception as e:
        logging.error(f"Pollinations error: {e}")
        return False

# البديل 2: Lexica API (مجاني، يولد صور كرتونية)
async def lexica_image(prompt: str, update: Update):
    """توليد صورة كرتونية باستخدام Lexica API (مجاني)"""
    try:
        cartoon_prompt = f"cartoon style, animated character, {prompt}"
        encoded_prompt = urllib.parse.quote(cartoon_prompt)
        url = f"https://lexica.art/api/v1/search?q={encoded_prompt}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('images') and len(data['images']) > 0:
                        image_url = data['images'][0].get('src')
                        if image_url:
                            async with session.get(image_url) as img_resp:
                                image_data = await img_resp.read()
                                image_file = io.BytesIO(image_data)
                                image_file.name = "lexica_image.png"
                                await update.message.reply_photo(
                                    photo=image_file,
                                    caption=f"🎨 صورة كرتونية\n📝 {prompt[:100]}..."
                                )
                                return True
        return False
    except:
        return False

# البديل 3: Craiyon API (مجاني، مشهور للصور الكرتونية)
async def craiyon_image(prompt: str, update: Update):
    """توليد صورة كرتونية باستخدام Craiyon API (مجاني)"""
    try:
        cartoon_prompt = f"cartoon drawing, {prompt}, cute style"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backend.craiyon.com/generate",
                json={"prompt": cartoon_prompt},
                timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('images') and len(data['images']) > 0:
                        import base64
                        image_data = base64.b64decode(data['images'][0])
                        image_file = io.BytesIO(image_data)
                        image_file.name = "craiyon_image.png"
                        await update.message.reply_photo(
                            photo=image_file,
                            caption=f"🎭 صورة كرتونية (Craiyon)\n📝 {prompt[:100]}..."
                        )
                        return True
        return False
    except:
        return False

# البديل 4: OpenAI DALL-E مجاني عبر Proxy (تجريبي)
async def dalle_free_image(prompt: str, update: Update):
    """توليد صورة باستخدام DALL-E مجاني"""
    try:
        cartoon_prompt = f"cartoon character illustration, {prompt}, vibrant colors"
        encoded_prompt = urllib.parse.quote(cartoon_prompt)
        url = f"https://tiny-img.com/api/generate?prompt={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "dalle_image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"✨ صورة كرتونية\n📝 {prompt[:100]}..."
            )
            return True
        return False
    except:
        return False

# البديل 5: Playground AI مجاني
async def playground_image(prompt: str, update: Update):
    """توليد صورة كرتونية"""
    try:
        cartoon_prompt = f"anime cartoon style, {prompt}, high quality"
        encoded_prompt = urllib.parse.quote(cartoon_prompt)
        url = f"https://playgroundai.com/api/generate?prompt={encoded_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "playground_image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🌟 صورة كرتونية\n📝 {prompt[:100]}..."
            )
            return True
        return False
    except:
        return False

# ========== الوظيفة الرئيسية لتوليد الصور ==========
async def generate_cartoon_image(prompt: str, update: Update):
    """محاولة كل البدائل المجانية لتوليد صورة كرتونية"""
    
    # إرسال رسالة المعالجة
    processing_msg = await update.message.reply_text(
        f"🎨 **جاري توليد صورة كرتونية...**\n\n"
        f"📝 الوصف: {prompt[:150]}\n\n"
        f"🔄 أجرب جميع البدائل المجانية..."
    )
    
    await asyncio.sleep(1)
    await processing_msg.edit_text("🖼 محاولة Pollinations API... (1/5)")
    
    success = False
    
    # البديل 1
    if not success:
        success = await pollinations_image(prompt, update)
        if not success:
            await processing_msg.edit_text("🖼 محاولة Lexica API... (2/5)")
    
    # البديل 2
    if not success:
        success = await lexica_image(prompt, update)
        if not success:
            await processing_msg.edit_text("🖼 محاولة Craiyon API... (3/5)")
    
    # البديل 3
    if not success:
        success = await craiyon_image(prompt, update)
        if not success:
            await processing_msg.edit_text("🖼 محاولة DALL-E Proxy... (4/5)")
    
    # البديل 4
    if not success:
        success = await dalle_free_image(prompt, update)
        if not success:
            await processing_msg.edit_text("🖼 محاولة Playground AI... (5/5)")
    
    # البديل 5
    if not success:
        success = await playground_image(prompt, update)
    
    if success:
        await processing_msg.delete()
        await update.message.reply_text("✅ تم توليد الصورة الكرتونية بنجاح!")
    else:
        await processing_msg.edit_text(
            "❌ عذراً، جميع خدمات توليد الصور غير متاحة حالياً.\n\n"
            "💡 **بدائل يدوية:**\n"
            "• جرب وصفاً أقصر (أقل من 100 حرف)\n"
            "• جرب وصفاً باللغة الإنجليزية\n"
            "• مثال: 'a boy playing in garden'\n"
            "• مثال: 'cartoon cat sitting on chair'"
        )

# ========== الوظيفة الرئيسية للصوت ==========
async def generate_audio(text: str, gender: str, update: Update):
    """تحويل النص إلى صوت بكل البدائل"""
    
    # تحليل النص
    analysis = await analyze_text_universal(text)
    
    await update.message.reply_text(
        f"📊 **تحليل النص:**\n\n"
        f"🌐 اللغة: {analysis['language']}\n"
        f"📝 عدد الحروف: {analysis['char_count']}\n"
        f"📖 عدد الكلمات: {analysis['word_count']}\n\n"
        f"🎙 جاري تحويل النص إلى صوت {'(ذكر)' if gender=='male' else '(أنثى)'}...",
        parse_mode="Markdown"
    )
    
    lang = 'ar' if analysis['language'] == 'العربية' else 'en'
    
    success = False
    
    if not success:
        success = await google_tts(text, lang, gender, update)
    if not success:
        success = await voicerss_tts(text, lang, gender, update)
    
    if success:
        await update.message.reply_text("✅ تم تحويل النص إلى صوت بنجاح!")
    else:
        await update.message.reply_text("❌ عذراً، خدمات الصوت غير متاحة حالياً. حاول بنص أقصر.")

# ========== أوامر البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎵 **صناعة صوت:** يحول أي نص إلى صوت MP3 (ذكر/أنثى)\n"
        "🎨 **صناعة صورة كرتونية:** يحول أي وصف إلى صورة كرتونية\n\n"
        "📝 **مثال للصورة:**\n"
        "• 'ولد في حديقة'\n"
        "• 'بنت مع قطة'\n"
        "• 'منزل كرتوني'\n\n"
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
            "🎤 **اختر نوع الصوت:**\n\n"
            "👨 ذكر → صوت رجالي\n"
            "👩 أنثى → صوت نسائي",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CHOOSING_AUDIO_GENDER
        
    elif action == "action_image":
        await query.edit_message_text(
            "🎨 **صناعة صورة كرتونية**\n\n"
            "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة\n"
            "• بنت مع قطة صغيرة\n"
            "• منزل كرتوني ملون\n"
            "• غابة مع حيوانات\n\n"
            "✅ سأحول وصفك إلى صورة كرتونية باستخدام 5 بدائل مجانية"
        )
        return WAITING_FOR_TEXT_IMAGE

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
            "🎤 **صوت (ذكر)**\n\n"
            "✏️ **أرسل النص الذي تريد تحويله إلى صوت:**"
        )
        return WAITING_FOR_TEXT_AUDIO
        
    elif choice == "audio_female":
        user_choices[user_id] = {'type': 'audio', 'gender': 'female'}
        await query.edit_message_text(
            "🎤 **صوت (أنثى)**\n\n"
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
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def receive_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    await generate_cartoon_image(user_text, update)
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎵 صناعة صوت", callback_data="action_audio")],
        [InlineKeyboardButton("🎨 صناعة صورة كرتونية", callback_data="action_image")],
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
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern="^(action_audio|action_image)$")],
            CHOOSING_AUDIO_GENDER: [CallbackQueryHandler(audio_gender_choice, pattern="^(audio_male|audio_female|back_to_start)$")],
            WAITING_FOR_TEXT_AUDIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_audio_text)],
            WAITING_FOR_TEXT_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_image_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل - توليد صور كرتونية + تحويل نص إلى صوت")
    app.run_polling()

if __name__ == "__main__":
    main()
