import express from 'express';
import fetch from 'node-fetch';
import dotenv from 'dotenv';
import { createClient } from '@supabase/supabase-js';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
app.use(express.json());
app.use(express.static('public'));

// ========== الإعدادات ==========
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const PORT = process.env.PORT || 3000;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

// ========== نظام تدوير مفاتيح AI ==========
const AI_KEYS = {
  deepseek: process.env.DEEPSEEK_API_KEY,
  openrouter: process.env.OPENROUTER_API_KEY,
  gemini: process.env.GEMINI_API_KEY,
};

let currentKeyIndex = 0;
const keyNames = ['deepseek', 'openrouter', 'gemini'];
const keyRotationStatus = { deepseek: 0, openrouter: 0, gemini: 0 };

function getNextAIKey() {
  const startIndex = currentKeyIndex;
  
  do {
    const keyName = keyNames[currentKeyIndex];
    const key = AI_KEYS[keyName];
    currentKeyIndex = (currentKeyIndex + 1) % keyNames.length;
    
    if (key && keyRotationStatus[keyName] < 50) {
      return { key, name: keyName };
    }
  } while (currentKeyIndex !== startIndex);
  
  // كل المفاتيح خلصت، نعيد العداد
  keyNames.forEach(k => keyRotationStatus[k] = 0);
  return { key: AI_KEYS.deepseek, name: 'deepseek' };
}

async function callAI(prompt, systemPrompt = null) {
  const { key, name } = getNextAIKey();
  
  let endpoint, headers, body;
  
  if (name === 'deepseek') {
    endpoint = 'https://api.deepseek.com/v1/chat/completions';
    headers = { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' };
    body = { model: 'deepseek-chat', messages: [], max_tokens: 2000 };
  } else if (name === 'openrouter') {
    endpoint = 'https://openrouter.ai/api/v1/chat/completions';
    headers = { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' };
    body = { model: 'google/gemini-2.0-flash-exp:free', messages: [] };
  } else {
    endpoint = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`;
    headers = { 'Content-Type': 'application/json' };
  }
  
  try {
    let response;
    
    if (name === 'gemini') {
      const contents = [];
      if (systemPrompt) contents.push({ role: 'user', parts: [{ text: systemPrompt }] });
      contents.push({ role: 'user', parts: [{ text: prompt }] });
      
      response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ contents })
      });
    } else {
      const messages = [];
      if (systemPrompt) messages.push({ role: 'system', content: systemPrompt });
      messages.push({ role: 'user', content: prompt });
      
      response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ ...body, messages })
      });
    }
    
    if (!response.ok) {
      keyRotationStatus[name]++;
      throw new Error(`${name} API failed`);
    }
    
    const data = await response.json();
    keyRotationStatus[name] = 0;
    
    if (name === 'gemini') {
      return data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    } else {
      return data.choices?.[0]?.message?.content || '';
    }
  } catch (error) {
    console.error(`AI call failed for ${name}:`, error.message);
    keyRotationStatus[name] += 10;
    return callAI(prompt, systemPrompt);
  }
}

// ========== بدائل مجانية للصور ==========
async function generateImage(prompt) {
  // نستخدم خدمة مجانية مثل Pollinations.ai
  const encodedPrompt = encodeURIComponent(`${prompt}, cartoon style, colorful, educational, 1024x1024`);
  
  try {
    const response = await fetch(`https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&nologo=true`);
    if (!response.ok) throw new Error('Image generation failed');
    
    const buffer = await response.arrayBuffer();
    return Buffer.from(buffer);
  } catch (error) {
    console.error('Image generation error:', error);
    // صورة بديلة
    const response = await fetch('https://picsum.photos/1024/1024');
    const buffer = await response.arrayBuffer();
    return Buffer.from(buffer);
  }
}

// ========== بدائل مجانية للصوت ==========
async function generateTTS(text, lang = 'ar') {
  // نستخدم Google Translate TTS المجاني
  const chunks = chunkText(text, 200);
  const audioBuffers = [];
  
  for (const chunk of chunks) {
    const url = `https://translate.google.com/translate_tts?ie=UTF-8&q=${encodeURIComponent(chunk)}&tl=${lang}&client=tw-ob&ttsspeed=0.9`;
    
    try {
      const response = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' }
      });
      
      if (response.ok) {
        const buffer = await response.arrayBuffer();
        audioBuffers.push(Buffer.from(buffer));
      }
    } catch (error) {
      console.error('TTS chunk error:', error);
    }
  }
  
  if (audioBuffers.length === 0) return null;
  return Buffer.concat(audioBuffers);
}

function chunkText(text, maxLength) {
  const sentences = text.split(/[.،!؟\n]+/).filter(s => s.trim());
  const chunks = [];
  let current = '';
  
  for (const s of sentences) {
    const trimmed = s.trim();
    if (!trimmed) continue;
    
    if (current.length + trimmed.length + 2 > maxLength) {
      if (current) chunks.push(current.trim());
      current = trimmed;
    } else {
      current += (current ? '. ' : '') + trimmed;
    }
  }
  
  if (current.trim()) chunks.push(current.trim());
  return chunks.length > 0 ? chunks : [text.substring(0, maxLength)];
}

// ========== لهجات ==========
const DIALECTS = {
  iraqi: { name: '🇮🇶 عراقي', prompt: 'اكتب بأسلوب عراقي ودود. استخدم: هسه، شلون، اكو، ماكو، يا حبيبي' },
  egyptian: { name: '🇪🇬 مصري', prompt: 'اكتب بأسلوب مصري ودود. استخدم: ازيك، يعني، كده، يا باشا' },
  syrian: { name: '🇸🇾 سوري', prompt: 'اكتب بأسلوب سوري ودود. استخدم: كيفك، هلق، منيح' },
  gulf: { name: '🇸🇦 خليجي', prompt: 'اكتب بأسلوب خليجي ودود. استخدم: وش، حلو، الحين، زين' },
  formal: { name: '📖 فصحى', prompt: 'اكتب بالعربية الفصحى الميسرة' },
  english: { name: '🇬🇧 English', prompt: 'Write in friendly educational English' },
};

// ========== Telegram Webhook ==========
app.post('/webhook', async (req, res) => {
  res.sendStatus(200);
  
  const update = req.body;
  console.log('Update:', JSON.stringify(update).substring(0, 200));
  
  if (update.callback_query) {
    await handleCallback(update.callback_query);
    return;
  }
  
  if (update.message) {
    await handleMessage(update.message);
  }
});

async function handleCallback(callback) {
  const chatId = callback.message?.chat?.id;
  const data = callback.data;
  
  if (data?.startsWith('dialect:')) {
    const dialect = data.split(':')[1];
    const name = DIALECTS[dialect]?.name || dialect;
    
    await supabase.from('user_preferences').upsert({
      chat_id: chatId,
      dialect,
      updated_at: new Date().toISOString()
    }, { onConflict: 'chat_id' });
    
    await answerCallback(callback.id, `✅ تم اختيار ${name}`);
    await sendMessage(chatId, `✅ ممتاز! اخترت ${name}\n\n📚 أرسل لي محاضرة (ملف أو نص) وأحولها لفيديو!\n\n💡 تغيير اللهجة: /dialect`);
  }
}

async function handleMessage(message) {
  const chatId = message.chat.id;
  const text = message.text || '';
  const document = message.document;
  
  if (text === '/start' || text === '/dialect') {
    await sendDialectKeyboard(chatId);
    return;
  }
  
  // جلب تفضيلات المستخدم
  const { data: pref } = await supabase
    .from('user_preferences')
    .select('dialect')
    .eq('chat_id', chatId)
    .single();
  
  if (!pref) {
    await sendDialectKeyboard(chatId);
    return;
  }
  
  const isLecture = document || (text && text.length > 50);
  
  if (!isLecture) {
    await sendMessage(chatId, '👋 أرسل لي محاضرة (نص طويل أو ملف) وأحولها لفيديو تعليمي!\n\n💡 /dialect لتغيير اللهجة');
    return;
  }
  
  // بدء المعالجة
  await sendMessage(chatId, `📚 وصلت المحاضرة!\n🎬 جاري إنشاء الفيديو باللهجة ${DIALECTS[pref.dialect]?.name}...\n⏳ انتظر 2-3 دقائق`);
  
  // معالجة في الخلفية
  processLecture(chatId, message, pref.dialect).catch(console.error);
}

async function processLecture(chatId, message, dialect) {
  try {
    // استخراج النص
    let content = message.text || '';
    if (message.document?.file_id) {
      content = await downloadDocument(message.document.file_id);
    }
    
    if (!content || content.length < 50) {
      await sendMessage(chatId, '😔 ما قدرت أقرأ المحتوى. أرسل نص أطول.');
      return;
    }
    
    await sendMessage(chatId, '🔍 جاري تحليل المحاضرة...');
    
    // تحليل المحاضرة
    const sections = await analyzeLecture(content, dialect);
    
    if (!sections || sections.length === 0) {
      await sendMessage(chatId, '😔 ما قدرت أحلل المحاضرة. جرب مرة ثانية.');
      return;
    }
    
    await sendMessage(chatId, `🎉 فهمت المحاضرة! ${sections.length} أقسام\n🎨 جاري إنشاء الصور والصوت...`);
    
    // إنشاء lecture record
    const { data: lecture } = await supabase
      .from('lectures')
      .insert({
        chat_id: chatId,
        title: sections[0]?.title || 'محاضرة',
        dialect,
        sections: [],
        status: 'processing'
      })
      .select('id')
      .single();
    
    const lectureId = lecture.id;
    const sectionData = [];
    
    // معالجة كل قسم
    for (let i = 0; i < sections.length; i++) {
      const section = sections[i];
      const idx = i + 1;
      
      try {
        // إنشاء صورة
        const imagePrompt = `Educational cartoon: ${section.caricature_description || section.title}. Colorful, cute style. Section ${idx}/${sections.length}`;
        const imageBuffer = await generateImage(imagePrompt);
        
        let imageUrl = '';
        if (imageBuffer) {
          const imgPath = `${lectureId}/section_${idx}.png`;
          const { error } = await supabase.storage
            .from('lecture-media')
            .upload(imgPath, imageBuffer, { contentType: 'image/png', upsert: true });
          
          if (!error) {
            const { data } = supabase.storage.from('lecture-media').getPublicUrl(imgPath);
            imageUrl = data.publicUrl;
          }
        }
        
        // إنشاء صوت
        const narration = `${section.title}. ${section.explanation}`;
        const audioBuffer = await generateTTS(narration, dialect === 'english' ? 'en' : 'ar');
        
        let audioUrl = '';
        if (audioBuffer) {
          const audioPath = `${lectureId}/section_${idx}.mp3`;
          const { error } = await supabase.storage
            .from('lecture-media')
            .upload(audioPath, audioBuffer, { contentType: 'audio/mpeg', upsert: true });
          
          if (!error) {
            const { data } = supabase.storage.from('lecture-media').getPublicUrl(audioPath);
            audioUrl = data.publicUrl;
          }
        }
        
        sectionData.push({
          index: idx,
          title: section.title,
          keywords: section.keywords || [],
          explanation: section.explanation,
          key_points: section.key_points || [],
          image_url: imageUrl,
          audio_url: audioUrl,
        });
        
        await sendMessage(chatId, `✅ تم قسم ${idx}/${sections.length}`);
        
      } catch (err) {
        console.error(`Section ${idx} error:`, err);
        sectionData.push({
          index: idx,
          title: section.title,
          keywords: section.keywords || [],
          explanation: section.explanation,
          key_points: section.key_points || [],
          image_url: '',
          audio_url: '',
        });
      }
    }
    
    // حفظ المحاضرة
    await supabase
      .from('lectures')
      .update({ sections: sectionData, status: 'completed' })
      .eq('id', lectureId);
    
    // رابط المشاهدة
    const videoUrl = `${APP_URL}/view/${lectureId}`;
    
    // إرسال النتيجة
    const summary = sections.map((s, i) => 
      `${i+1}. <b>${s.title}</b>\n   🔑 ${(s.keywords || []).join('، ')}`
    ).join('\n\n');
    
    await sendMessage(chatId, 
      `🎬 <b>تم إنشاء الفيديو!</b>\n\n📋 <b>ملخص:</b>\n${summary}\n\n🔗 <b>شاهد:</b>\n${videoUrl}\n\n✅ أرسل محاضرة ثانية!`,
      'HTML'
    );
    
  } catch (error) {
    console.error('Process error:', error);
    await sendMessage(chatId, '😔 حدث خطأ. جرب مرة ثانية.');
  }
}

async function analyzeLecture(text, dialect) {
  const dialectPrompt = DIALECTS[dialect]?.prompt || DIALECTS.formal.prompt;
  
  const systemPrompt = `أنت محلل محاضرات محترف.
${dialectPrompt}

حلل النص وقسمه لـ 3-6 أقسام. لكل قسم:
- title: عنوان
- keywords: 3-5 كلمات مفتاحية
- explanation: شرح مفصل (5-8 جمل)
- key_points: 2-4 نقاط مهمة
- caricature_description: وصف لصورة كاريكاتيرية (بالإنجليزية)

أعد JSON: {"sections": [...]}`;

  const response = await callAI(text.substring(0, 10000), systemPrompt);
  
  try {
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      return parsed.sections || [];
    }
  } catch (e) {
    console.error('Parse error:', e);
  }
  
  return [];
}

async function downloadDocument(fileId) {
  const fileRes = await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/getFile?file_id=${fileId}`);
  const fileData = await fileRes.json();
  
  if (!fileData.ok) return '';
  
  const filePath = fileData.result.file_path;
  const dlRes = await fetch(`https://api.telegram.org/file/bot${TELEGRAM_TOKEN}/${filePath}`);
  const buffer = await dlRes.arrayBuffer();
  
  // محاولة قراءة النص
  const text = new TextDecoder().decode(buffer);
  
  // إذا كان PDF أو مستند
  if (text.includes('PDF') || filePath.endsWith('.pdf')) {
    // نستخدم AI لاستخراج النص
    const base64 = Buffer.from(buffer.slice(0, 50000)).toString('base64');
    const response = await callAI('استخرج النص من هذا المستند', 'أنت مساعد لاستخراج النصوص');
    return response;
  }
  
  return text;
}

// ========== Telegram API Helpers ==========
async function sendMessage(chatId, text, parseMode = null) {
  const body = { chat_id: chatId, text };
  if (parseMode) body.parse_mode = parseMode;
  
  await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

async function sendDialectKeyboard(chatId) {
  await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text: '👋 يا هلا!\n\n🗣️ اختر اللهجة:',
      reply_markup: {
        inline_keyboard: [
          [{ text: '🇮🇶 عراقي', callback_data: 'dialect:iraqi' }, { text: '🇪🇬 مصري', callback_data: 'dialect:egyptian' }],
          [{ text: '🇸🇾 سوري', callback_data: 'dialect:syrian' }, { text: '🇸🇦 خليجي', callback_data: 'dialect:gulf' }],
          [{ text: '📖 فصحى', callback_data: 'dialect:formal' }, { text: '🇬🇧 English', callback_data: 'dialect:english' }],
        ]
      }
    })
  });
}

async function answerCallback(callbackId, text) {
  await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackId, text })
  });
}

// ========== واجهة المشاهدة ==========
app.get('/view/:id', async (req, res) => {
  const { id } = req.params;
  
  const { data: lecture } = await supabase
    .from('lectures')
    .select('*')
    .eq('id', id)
    .single();
  
  if (!lecture) {
    return res.status(404).send('المحاضرة غير موجودة');
  }
  
  const sections = lecture.sections || [];
  
  res.send(`
<!DOCTYPE html>
<html dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${lecture.title}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
      color: white;
      min-height: 100vh;
    }
    .header {
      background: rgba(0,0,0,0.3);
      padding: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .progress {
      height: 4px;
      background: rgba(255,255,255,0.1);
    }
    .progress-bar {
      height: 100%;
      background: #3b82f6;
      transition: width 0.3s;
      width: 0%;
    }
    .section {
      display: none;
      padding: 1rem;
    }
    .section.active {
      display: block;
    }
    .section img {
      width: 100%;
      max-height: 40vh;
      object-fit: contain;
      border-radius: 12px;
      margin-bottom: 1rem;
    }
    .keywords {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 1rem 0;
    }
    .keyword {
      background: rgba(59,130,246,0.2);
      color: #93c5fd;
      padding: 0.25rem 0.75rem;
      border-radius: 20px;
      font-size: 0.8rem;
    }
    .controls {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(0,0,0,0.5);
      padding: 1rem;
      display: flex;
      justify-content: center;
      gap: 2rem;
    }
    .controls button {
      background: #3b82f6;
      border: none;
      color: white;
      padding: 0.75rem 1.5rem;
      border-radius: 50px;
      font-size: 1rem;
      cursor: pointer;
    }
    .controls button:disabled {
      opacity: 0.5;
    }
    .summary {
      padding: 1rem;
    }
    .summary-item {
      background: rgba(255,255,255,0.05);
      padding: 1rem;
      border-radius: 12px;
      margin-bottom: 1rem;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="header">
    <h3>${lecture.title}</h3>
    <span id="counter">1/${sections.length}</span>
  </div>
  <div class="progress">
    <div class="progress-bar" id="progress"></div>
  </div>
  
  <div id="content"></div>
  
  <div class="controls">
    <button id="prevBtn" onclick="prevSection()">⏮ السابق</button>
    <button id="playBtn" onclick="togglePlay()">▶ تشغيل</button>
    <button id="nextBtn" onclick="nextSection()">التالي ⏭</button>
  </div>
  
  <audio id="audio"></audio>
  
  <script>
    const sections = ${JSON.stringify(sections)};
    let currentIndex = 0;
    let isPlaying = false;
    const audio = document.getElementById('audio');
    
    function renderSection(index) {
      const s = sections[index];
      if (!s) return;
      
      const isLast = index === sections.length - 1;
      
      if (isLast) {
        // عرض الملخص
        document.getElementById('content').innerHTML = \`
          <div class="summary">
            <h2 style="margin-bottom:1rem">📋 ملخص المحاضرة</h2>
            \${sections.map((sec, i) => \`
              <div class="summary-item" onclick="goToSection(\${i})">
                <strong>\${i+1}. \${sec.title}</strong>
                <div class="keywords">
                  \${(sec.keywords || []).map(k => \`<span class="keyword">\${k}</span>\`).join('')}
                </div>
              </div>
            \`).join('')}
          </div>
        \`;
      } else {
        document.getElementById('content').innerHTML = \`
          <div class="section active">
            \${s.image_url ? \`<img src="\${s.image_url}" alt="\${s.title}">\` : ''}
            <h2 style="color:#93c5fd;margin-bottom:1rem">\${s.title}</h2>
            <p style="line-height:1.6;margin-bottom:1rem">\${s.explanation}</p>
            \${s.key_points ? \`
              <div style="background:rgba(255,255,255,0.05);padding:1rem;border-radius:12px">
                <h4 style="color:#93c5fd;margin-bottom:0.5rem">💡 أهم النقاط:</h4>
                <ul style="list-style:none">
                  \${s.key_points.map(p => \`<li style="margin-bottom:0.25rem">• \${p}</li>\`).join('')}
                </ul>
              </div>
            \` : ''}
            <div class="keywords">
              \${(s.keywords || []).map(k => \`<span class="keyword">🔑 \${k}</span>\`).join('')}
            </div>
          </div>
        \`;
      }
      
      document.getElementById('counter').textContent = \`\${index+1}/\${sections.length}\`;
      document.getElementById('progress').style.width = \`\${((index+1)/sections.length)*100}%\`;
      
      // تحميل الصوت
      if (s.audio_url && !isLast) {
        audio.src = s.audio_url;
      }
    }
    
    function goToSection(index) {
      currentIndex = index;
      renderSection(index);
      isPlaying = false;
      document.getElementById('playBtn').textContent = '▶ تشغيل';
    }
    
    function prevSection() {
      if (currentIndex > 0) {
        currentIndex--;
        renderSection(currentIndex);
      }
    }
    
    function nextSection() {
      if (currentIndex < sections.length - 1) {
        currentIndex++;
        renderSection(currentIndex);
        if (isPlaying) audio.play();
      } else if (currentIndex === sections.length - 1) {
        // عرض الملخص
        renderSection(currentIndex);
      }
    }
    
    function togglePlay() {
      if (isPlaying) {
        audio.pause();
        document.getElementById('playBtn').textContent = '▶ تشغيل';
      } else {
        audio.play();
        document.getElementById('playBtn').textContent = '⏸ إيقاف';
      }
      isPlaying = !isPlaying;
    }
    
    audio.onended = () => {
      if (currentIndex < sections.length - 1) {
        nextSection();
        if (isPlaying) audio.play();
      } else {
        isPlaying = false;
        document.getElementById('playBtn').textContent = '▶ تشغيل';
      }
    };
    
    // البداية
    renderSection(0);
  </script>
</body>
</html>
  `);
});

// ========== إعداد webhook ==========
app.get('/setup', async (req, res) => {
  const webhookUrl = `${APP_URL}/webhook`;
  
  const response = await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: webhookUrl })
  });
  
  const data = await response.json();
  res.json({ webhookUrl, ...data });
});

// ========== الصفحة الرئيسية ==========
app.get('/', (req, res) => {
  res.send(`
<!DOCTYPE html>
<html dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>بوت المحاضرات الذكي</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
      color: white;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 2rem;
    }
    .container { max-width: 600px; }
    h1 {
      font-size: 2.5rem;
      margin-bottom: 1rem;
      background: linear-gradient(to left, #60a5fa, #34d399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .bot-icon {
      width: 80px;
      height: 80px;
      background: rgba(59,130,246,0.2);
      border-radius: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 1.5rem;
      font-size: 2.5rem;
      border: 1px solid rgba(59,130,246,0.3);
    }
    .btn {
      display: inline-block;
      background: #3b82f6;
      color: white;
      padding: 1rem 2rem;
      border-radius: 12px;
      text-decoration: none;
      margin-top: 2rem;
      font-weight: bold;
    }
    .features {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
      margin: 2rem 0;
    }
    .feature {
      background: rgba(255,255,255,0.05);
      padding: 1.5rem 1rem;
      border-radius: 12px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="bot-icon">🤖</div>
    <h1>بوت المحاضرات الذكي</h1>
    <p style="opacity:0.8">حوّل أي محاضرة إلى فيديو تعليمي مع رسومات وصوت باللهجة اللي تحبها</p>
    
    <div class="features">
      <div class="feature">📚 أرسل محاضرة</div>
      <div class="feature">🎨 تحليل ذكي</div>
      <div class="feature">🎬 فيديو تعليمي</div>
    </div>
    
    <a href="https://t.me/${process.env.TELEGRAM_BOT_USERNAME || 'your_bot'}" class="btn">💬 ابدأ مع البوت</a>
    <p style="margin-top:1rem;opacity:0.5;font-size:0.9rem">مجاني بالكامل</p>
  </div>
</body>
</html>
  `);
});

// ========== تشغيل السيرفر ==========
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Setup webhook: ${APP_URL}/setup`);
});
