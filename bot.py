import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين بيانات المستخدمين مؤقتاً
user_data = {}

# ========== توليد الصورة من Pollinations ==========
async def generate_image(prompt: str, update: Update):
    """توليد صورة من النص"""
    try:
        # ترميز النص
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style, colorful")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        
        # طلب الصورة
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()
        
        if len(image_data) > 1000:
            image_file = io.BytesIO(image_data)
            image_file.name = "image.png"
            await update.message.reply_photo(
                photo=image_file,
                caption=f"🎨 **تم توليد الصورة!**\n\n📝 {prompt[:150]}..."
            )
            return True
        return False
    except Exception as e:
        logger.error(f"خطأ في توليد الصورة: {e}")
        return False

# ========== تحويل النص إلى صوت ==========
async def generate_audio(text: str, gender: str, update: Update):
    """تحويل النص إلى صوت"""
    try:
        # تحديد اللغة
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
        lang = 'ar' if has_arabic else 'en'
        
        # ترميز النص
        text_encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        # طلب الصوت
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
        logger.error(f"خطأ في تحويل الصوت: {e}")
        return False

# ========== تحليل النص ==========
async def analyze_text(text: str, update: Update):
    """تحليل النص وإعطاء إحصائيات"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    analysis = f"""
📊 **تحليل النص**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص:**
{text[:300]}{'...' if len(text) > 300 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📈 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━
📏 **الطول:** {'قصير' if len(words) < 15 else 'متوسط' if len(words) < 40 else 'طويل'}

✅ تم التحليل بنجاح
"""
    await update.message.reply_text(analysis)

# ========== شرح النص (متقدم) ==========
async def explain_text(text: str, update: Update):
    """شرح مفصل للنص"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    # حساب الكلمات الأكثر تكراراً
    word_freq = {}
    for word in words:
        w = word.lower()
        word_freq[w] = word_freq.get(w, 0) + 1
    
    common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # تحليل المشاعر البسيط
    positive = ['جميل', 'رائع', 'سعيد', 'حب', 'good', 'happy', 'love', 'beautiful']
    negative = ['سيء', 'حزين', 'صعب', 'bad', 'sad', 'hard', 'terrible']
    
    pos_count = sum(1 for w in words if w.lower() in positive)
    neg_count = sum(1 for w in words if w.lower() in negative)
    
    if pos_count > neg_count:
        sentiment = "😊 إيجابي"
    elif neg_count > pos_count:
        sentiment = "😔 سلبي"
    else:
        sentiment = "😐 محايد"
    
    explanation = f"""
📚 **شرح وتحليل النص (مفصل)**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:500]}{'...' if len(text) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• متوسط طول الكلمة: {sum(len(w) for w in words) / len(words):.1f} حروف

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔝 **الكلمات الأكثر تكراراً:**
"""
    for word, count in common_words:
        explanation += f"• '{word}': {count} مرات\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎭 **تحليل المشاعر:** {sentiment}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص النص:**
{text[:200]}{'...' if len(text) > 200 else ''}

✅ تم التحليل والشرح بنجاح
"""
    await update.message.reply_text(explanation)

# ========== معالجة الأزرار ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data
    
    if action == "image":
        await query.edit_message_text(
            "🎨 **توليد صورة من النص**\n\n"
            "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة مع زهور\n"
            "• قطة نائمة على كنبة\n"
            "• غابة مع حيوانات\n\n"
            "✅ سأقوم بتوليد صورة حسب وصفك"
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
            "🎤 **تم اختيار صوت (ذكر)**\n\n"
            "✏️ **أرسل النص الذي تريد تحويله إلى صوت:**"
        )
        user_data[user_id] = {'mode': 'audio', 'gender': 'male'}
        
    elif action == "audio_female":
        await query.edit_message_text(
            "🎤 **تم اختيار صوت (أنثى)**\n\n"
            "✏️ **أرسل النص الذي تريد تحويله إلى صوت:**"
        )
        user_data[user_id] = {'mode': 'audio', 'gender': 'female'}
        
    elif action == "analyze":
        await query.edit_message_text(
            "📊 **تحليل النص**\n\n"
            "✏️ **أرسل النص لتحليله:**\n\n"
            "✅ سأقوم بتحليل النص وإعطائك إحصائيات عنه"
        )
        user_data[user_id] = {'mode': 'analyze'}
        
    elif action == "explain":
        await query.edit_message_text(
            "📚 **شرح وتحليل النص (مفصل)**\n\n"
            "✏️ **أرسل النص لشرحه وتحليله:**\n\n"
            "✅ سأقوم بشرح النص بالتفصيل مع:\n"
            "• عدد الكلمات والحروف والجمل\n"
            "• اللغة المكتشفة\n"
            "• الكلمات الأكثر تكراراً\n"
            "• تحليل المشاعر\n"
            "• ملخص النص"
        )
        user_data[user_id] = {'mode': 'explain'}
        
    elif action == "back":
        await show_menu(query)

async def show_menu(query):
    """عرض القائمة الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل للنص", callback_data="explain")],
    ]
    await query.edit_message_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة:** يحول وصفك إلى صورة\n"
        "🎵 **تحويل نص إلى صوت:** يحول النص إلى MP3 (ذكر/أنثى)\n"
        "📊 **تحليل النص:** يعطي إحصائيات سريعة\n"
        "📚 **شرح مفصل:** تحليل كامل مع مشاعر وكلمات متكررة\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # إذا كان المستخدم ليس في وضع معين، اعرض القائمة
    if user_id not in user_data:
        keyboard = [
            [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
            [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
            [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
            [InlineKeyboardButton("📚 شرح مفصل للنص", callback_data="explain")],
        ]
        await update.message.reply_text(
            "✨ **أهلاً بك!** ✨\n\n"
            "اختر ما تريد من الأزرار:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    mode_data = user_data[user_id]
    mode = mode_data.get('mode')
    
    # رسالة المعالجة
    processing = await update.message.reply_text("⏳ **جاري المعالجة...**")
    
    if mode == 'image':
        # توليد صورة
        success = await generate_image(text, update)
        if not success:
            await update.message.reply_text(
                "❌ **عذراً، لم أتمكن من توليد الصورة.**\n\n"
                "💡 نصائح:\n"
                "• جرب وصفاً أقصر (أقل من 200 حرف)\n"
                "• جرب وصفاً باللغة الإنجليزية\n"
                "• مثال: 'a boy playing in garden'"
            )
        
    elif mode == 'audio':
        # تحويل إلى صوت
        gender = mode_data.get('gender', 'male')
        success = await generate_audio(text, gender, update)
        if not success:
            await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً.")
        
    elif mode == 'analyze':
        # تحليل النص
        await analyze_text(text, update)
        
    elif mode == 'explain':
        # شرح مفصل
        await explain_text(text, update)
    
    await processing.delete()
    
    # حذف وضع المستخدم بعد المعالجة
    del user_data[user_id]
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل للنص", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== أمر /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل للنص", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت المتكامل!** ✨\n\n"
        "🎨 **توليد صورة:** يحول وصفك إلى صورة\n"
        "🎵 **تحويل نص إلى صوت:** يحول النص إلى MP3 (ذكر/أنثى)\n"
        "📊 **تحليل النص:** يعطي إحصائيات سريعة\n"
        "📚 **شرح مفصل:** تحليل كامل مع مشاعر وكلمات متكررة\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== أمر /help ==========
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **طريقة الاستخدام:**\n\n"
        "1️⃣ اضغط على /start\n"
        "2️⃣ اختر الخدمة التي تريدها من الأزرار\n"
        "3️⃣ أرسل النص أو الوصف المطلوب\n\n"
        "🔹 **الخدمات المتاحة:**\n"
        "• توليد صورة من النص\n"
        "• تحويل نص إلى صوت (ذكر/أنثى)\n"
        "• تحليل النص (إحصائيات سريعة)\n"
        "• شرح مفصل للنص (مشاعر + كلمات متكررة)"
    )

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 50)
    print("✅ البوت يعمل بنجاح!")
    print("📊 الخدمات: صور، صوت، تحليل، شرح مفصل")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    main()
