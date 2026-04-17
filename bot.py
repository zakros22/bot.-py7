import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import subprocess
import sys
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME")

# تخزين الطلبات المعلقة
pending_image_requests = {}

# ========== وظيفة إعادة تشغيل Heroku ==========
def restart_heroku():
    """إعادة تشغيل تطبيق Heroku بالكامل"""
    try:
        if HEROKU_APP_NAME:
            logger.info(f"🔄 جاري إعادة تشغيل {HEROKU_APP_NAME}...")
            
            # استخدام Heroku CLI
            result = subprocess.run(
                ["heroku", "restart", "-a", HEROKU_APP_NAME],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                logger.info("✅ تم إعادة التشغيل بنجاح")
                return True
            else:
                logger.error(f"فشل إعادة التشغيل: {result.stderr}")
                
            # طريقة بديلة: استخدام scale
            subprocess.run(
                ["heroku", "ps:scale", "worker=0", "-a", HEROKU_APP_NAME],
                capture_output=True, timeout=10
            )
            time.sleep(2)
            subprocess.run(
                ["heroku", "ps:scale", "worker=1", "-a", HEROKU_APP_NAME],
                capture_output=True, timeout=10
            )
            return True
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return False

# ========== توليد الصورة ==========
async def generate_image(prompt: str, update: Update):
    """توليد صورة من Pollinations"""
    try:
        clean_prompt = prompt.strip().replace(" ", "%20")
        encoded_prompt = urllib.parse.quote(f"{clean_prompt}, cartoon style")
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512"
        
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
        logger.error(f"خطأ في التوليد: {e}")
        return False

# ========== أمر توليد صورة (مع إعادة تشغيل مسبقة) ==========
async def start_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية توليد الصورة مع إعادة تشغيل مسبقة"""
    user_id = update.effective_user.id
    
    await update.message.reply_text(
        "🎨 **توليد صورة من النص**\n\n"
        "✏️ **أرسل وصف الصورة التي تريد:**\n\n"
        "📝 أمثلة:\n"
        "• ولد في حديقة مع زهور\n"
        "• قطة نائمة على كنبة\n"
        "• a boy playing in garden\n\n"
        "⚠️ **ملاحظة:** سيتم إعادة تشغيل الخادم قبل توليد الصورة لضمان العمل بشكل صحيح"
    )
    
    # حفظ أن المستخدم في وضع انتظار الصورة
    pending_image_requests[user_id] = {'waiting': True}

# ========== معالجة وصف الصورة ==========
async def handle_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة وصف الصورة وإعادة التشغيل ثم التوليد"""
    user_id = update.effective_user.id
    prompt = update.message.text
    
    if user_id not in pending_image_requests:
        return False
    
    del pending_image_requests[user_id]
    
    # إعلام المستخدم
    await update.message.reply_text(
        f"🎨 **جاري تحضير النظام...**\n\n"
        f"📝 وصفك: {prompt[:100]}...\n\n"
        f"🔄 **جاري إعادة تشغيل الخادم...**\n"
        f"⏱ سيستغرق هذا 5-10 ثواني\n\n"
        f"✅ بعد إعادة التشغيل، ستأتي الصورة تلقائياً"
    )
    
    # حفظ الطلب لإعادة المحاولة بعد إعادة التشغيل
    pending_image_requests[user_id] = {'prompt': prompt, 'chat_id': update.effective_chat.id}
    
    # إعادة تشغيل Heroku
    restart_heroku()
    
    # انتظار إعادة التشغيل
    await asyncio.sleep(5)
    
    # محاولة توليد الصورة بعد إعادة التشغيل
    success = await generate_image(prompt, update)
    
    if not success:
        await update.message.reply_text(
            "❌ **فشل توليد الصورة**\n\n"
            "💡 نصائح:\n"
            "• جرب وصفاً أقصر (أقل من 150 حرف)\n"
            "• جرب وصفاً باللغة الإنجليزية\n"
            "• مثال: 'a cat sleeping on a sofa'"
        )
    
    return True

# ========== تحويل النص إلى صوت ==========
async def start_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تحويل النص إلى صوت"""
    keyboard = [
        [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
        [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    await update.message.reply_text(
        "🎤 **تحويل نص إلى صوت**\n\nاختر نوع الصوت:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_audio_text(update: Update, context: ContextTypes.DEFAULT_TYPE, gender: str):
    """معالجة النص وتحويله إلى صوت"""
    text = update.message.text
    
    await update.message.reply_text(f"🎙 **جاري تحويل النص إلى صوت ({'ذكر' if gender=='male' else 'أنثى'})...**")
    
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
        else:
            await update.message.reply_text("❌ فشل تحويل النص إلى صوت")
    except Exception as e:
        logger.error(f"خطأ في الصوت: {e}")
        await update.message.reply_text("❌ عذراً، خدمة الصوت غير متاحة حالياً")

# ========== تحليل النص ==========
async def analyze_text(text: str, update: Update):
    """تحليل النص"""
    words = text.split()
    sentences = text.count('.') + text.count('!') + text.count('?') + text.count('؟')
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
• عدد الجمل: {sentences if sentences > 0 else 1}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

✅ تم التحليل بنجاح
"""
    await update.message.reply_text(analysis)

async def start_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 **تحليل النص**\n\n"
        "✏️ **أرسل النص لتحليله:**\n\n"
        "✅ سأقوم بتحليل النص وإعطائك:\n"
        "• عدد الحروف والكلمات والجمل\n"
        "• اللغة المكتشفة"
    )

# ========== شرح النص المتقدم ==========
async def explain_text(text: str, update: Update):
    """شرح مفصل للنص"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    # الكلمات الأكثر تكراراً
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    common = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:3]
    
    explanation = f"""
📚 **شرح مفصل للنص**

━━━━━━━━━━━━━━━━━━━━━━
📝 **النص:**
{text[:400]}{'...' if len(text) > 400 else ''}

━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}

━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━
🔝 **الكلمات الأكثر تكراراً:**
"""
    for word, count in common:
        explanation += f"• '{word}': {count} مرات\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص:**
{text[:150]}{'...' if len(text) > 150 else ''}

✅ تم الشرح بنجاح
"""
    await update.message.reply_text(explanation)

async def start_explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **شرح مفصل للنص**\n\n"
        "✏️ **أرسل النص لشرحه:**\n\n"
        "✅ سأقوم بإعطائك:\n"
        "• إحصائيات كاملة\n"
        "• الكلمات الأكثر تكراراً\n"
        "• ملخص النص"
    )

# ========== معالجة الأزرار ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    if action == "image":
        await query.edit_message_text(
            "🎨 **توليد صورة**\n\n"
            "✏️ **أرسل وصف الصورة:**\n\n"
            "📝 أمثلة:\n"
            "• ولد في حديقة\n"
            "• قطة نائمة\n"
            "• غابة مع حيوانات"
        )
        pending_image_requests[user_id] = {'waiting': True}
        
    elif action == "audio":
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await query.edit_message_text(
            "🎤 **اختر نوع الصوت:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif action == "audio_male":
        await query.edit_message_text(
            "🎤 **صوت ذكر**\n\n✏️ **أرسل النص:**"
        )
        pending_image_requests[user_id] = {'audio_gender': 'male'}
        
    elif action == "audio_female":
        await query.edit_message_text(
            "🎤 **صوت أنثى**\n\n✏️ **أرسل النص:**"
        )
        pending_image_requests[user_id] = {'audio_gender': 'female'}
        
    elif action == "analyze":
        await query.edit_message_text(
            "📊 **تحليل النص**\n\n✏️ **أرسل النص:**"
        )
        pending_image_requests[user_id] = {'analyze': True}
        
    elif action == "explain":
        await query.edit_message_text(
            "📚 **شرح مفصل**\n\n✏️ **أرسل النص:**"
        )
        pending_image_requests[user_id] = {'explain': True}
        
    elif action == "back":
        await show_menu(query)

async def show_menu(query):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل", callback_data="explain")],
    ]
    await query.edit_message_text(
        "✨ **مرحباً بك في البوت** ✨\n\n"
        "🎨 توليد صورة من النص\n"
        "🎵 تحويل نص إلى صوت\n"
        "📊 تحليل النص\n"
        "📚 شرح مفصل\n\n"
        "🔽 اختر ما تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # إذا كان المستخدم في وضع توليد الصورة
    if user_id in pending_image_requests:
        data = pending_image_requests[user_id]
        
        if data.get('waiting'):
            # توليد صورة مع إعادة تشغيل
            del pending_image_requests[user_id]
            await update.message.reply_text(f"🎨 **جاري التجهيز...**\n\n📝 {text[:100]}\n\n🔄 جاري إعادة تشغيل الخادم...")
            
            # إعادة تشغيل Heroku
            restart_heroku()
            await asyncio.sleep(5)
            
            # توليد الصورة
            success = await generate_image(text, update)
            if not success:
                await update.message.reply_text("❌ فشل توليد الصورة، حاول مرة أخرى")
            return
            
        elif 'audio_gender' in data:
            # تحويل إلى صوت
            gender = data['audio_gender']
            del pending_image_requests[user_id]
            await handle_audio_text(update, context, gender)
            return
            
        elif data.get('analyze'):
            # تحليل النص
            del pending_image_requests[user_id]
            await analyze_text(text, update)
            return
            
        elif data.get('explain'):
            # شرح مفصل
            del pending_image_requests[user_id]
            await explain_text(text, update)
            return
    
    # إذا لم يكن في وضع معين، اعرض القائمة
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **أهلاً بك!** ✨\n\nاختر ما تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== أمر /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📊 تحليل النص", callback_data="analyze")],
        [InlineKeyboardButton("📚 شرح مفصل", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **مرحباً بك في البوت** ✨\n\n"
        "🎨 توليد صورة من النص\n"
        "🎵 تحويل نص إلى صوت (ذكر/أنثى)\n"
        "📊 تحليل النص\n"
        "📚 شرح مفصل\n\n"
        "🔽 اختر ما تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 50)
    print("✅ البوت يعمل!")
    print(f"📊 تطبيق Heroku: {HEROKU_APP_NAME}")
    print("🎨 قبل كل صورة → إعادة تشغيل تلقائي")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    import re
    main()
