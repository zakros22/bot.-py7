import os
import re
import json
import logging
import random
from typing import List, Dict
from api_key_manager import key_manager

logger = logging.getLogger(__name__)

# محاولة استيراد المكتبات
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def detect_language(text: str) -> str:
    """كشف اللغة"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return 'en'
    return 'ar' if (arabic_chars / total_chars) > 0.25 else 'en'


def _extract_json_from_text(raw: str) -> str:
    """استخراج JSON من النص"""
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()
    start = raw.find('[')
    end = raw.rfind(']')
    if start != -1 and end != -1 and end > start:
        return raw[start:end + 1]
    return raw


def _parse_questions_json(json_text: str) -> list:
    """تحليل JSON للأسئلة"""
    try:
        questions = json.loads(json_text)
    except json.JSONDecodeError:
        fixed = re.sub(r',(\s*[}\]])', r'\1', json_text)
        try:
            questions = json.loads(fixed)
        except:
            return []
    
    if not isinstance(questions, list):
        return []
    
    valid = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if not q.get('question') or not q.get('correct_answer'):
            continue
        if not q.get('type'):
            q['type'] = 'multiple_choice'
        if q['type'] == 'multiple_choice' and not q.get('options'):
            # إنشاء خيارات افتراضية إذا لم تكن موجودة
            q['options'] = ['A) خيار 1', 'B) خيار 2', 'C) خيار 3', 'D) خيار 4']
        q.setdefault('explanation', '')
        valid.append(q)
    
    return valid


def _build_prompt(content: str, question_count: int, difficulty: str, language: str, question_types: list) -> str:
    """بناء النص الموجه"""
    diff_map_ar = {'easy': 'سهلة وبسيطة', 'medium': 'متوسطة الصعوبة', 'hard': 'صعبة ومتطلبة'}
    diff_map_en = {'easy': 'easy', 'medium': 'medium', 'hard': 'hard'}
    
    type_names_ar = {
        'multiple_choice': 'اختيار متعدد',
        'true_false': 'صح/خطأ',
        'fill_blank': 'ملء الفراغات',
        'qa': 'سؤال وجواب'
    }
    type_names_en = {
        'multiple_choice': 'Multiple Choice',
        'true_false': 'True/False',
        'fill_blank': 'Fill in Blank',
        'qa': 'Q&A'
    }
    
    type_names = type_names_ar if language == 'ar' else type_names_en
    types_list = ', '.join([type_names.get(t, t) for t in question_types])
    
    if language == 'ar':
        return f"""أنت خبير في إنشاء الاختبارات التعليمية.

المحتوى:
---
{content[:3500]}
---

الرجاء إنشاء {question_count} سؤال اختبار.
مستوى الصعوبة: {diff_map_ar.get(difficulty, 'متوسطة')}
أنواع الأسئلة المسموحة: {types_list}

قم بإرجاع JSON فقط بالصيغة:
[
  {{
    "type": "multiple_choice",
    "question": "نص السؤال",
    "options": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
    "correct_answer": "الإجابة الصحيحة",
    "explanation": "شرح الإجابة"
  }}
]

أعد JSON فقط، لا تكتب شيئاً آخر."""
    
    else:
        return f"""You are an expert quiz generator.

Content:
---
{content[:3500]}
---

Generate {question_count} quiz questions.
Difficulty: {diff_map_en.get(difficulty, 'medium')}
Question types: {types_list}

Return ONLY JSON:
[
  {{
    "type": "multiple_choice",
    "question": "Question text",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Correct answer",
    "explanation": "Explanation"
  }}
]

Return ONLY JSON, no other text."""


# ==================== Groq (Llama 3) - مجاني وسريع ====================

def generate_quiz_groq(content: str, question_count: int, difficulty: str, language: str, question_types: list, key_info: tuple) -> list:
    """توليد باستخدام Groq"""
    api_key, key_id = key_info
    
    client = Groq(api_key=api_key)
    prompt = _build_prompt(content, question_count, difficulty, language, question_types)
    
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096
    )
    
    raw = response.choices[0].message.content.strip()
    json_text = _extract_json_from_text(raw)
    questions = _parse_questions_json(json_text)
    
    if not questions:
        raise ValueError("No valid questions generated")
    
    return questions[:question_count]


# ==================== Gemini - مجاني ====================

def generate_quiz_gemini(content: str, question_count: int, difficulty: str, language: str, question_types: list, key_info: tuple) -> list:
    """توليد باستخدام Gemini"""
    api_key, key_id = key_info
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = _build_prompt(content, question_count, difficulty, language, question_types)
    response = model.generate_content(prompt)
    raw = response.text.strip()
    
    json_text = _extract_json_from_text(raw)
    questions = _parse_questions_json(json_text)
    
    if not questions:
        raise ValueError("No valid questions generated")
    
    return questions[:question_count]


# ==================== DeepSeek ====================

def generate_quiz_deepseek(content: str, question_count: int, difficulty: str, language: str, question_types: list, key_info: tuple) -> list:
    """توليد باستخدام DeepSeek"""
    api_key, key_id = key_info
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1"
    )
    
    prompt = _build_prompt(content, question_count, difficulty, language, question_types)
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096
    )
    
    raw = response.choices[0].message.content.strip()
    json_text = _extract_json_from_text(raw)
    questions = _parse_questions_json(json_text)
    
    return questions[:question_count]


# ==================== OpenRouter ====================

def generate_quiz_openrouter(content: str, question_count: int, difficulty: str, language: str, question_types: list, key_info: tuple) -> list:
    """توليد باستخدام OpenRouter"""
    api_key, key_id = key_info
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )
    
    prompt = _build_prompt(content, question_count, difficulty, language, question_types)
    
    response = client.chat.completions.create(
        model="mistralai/mistral-7b-instruct:free",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096
    )
    
    raw = response.choices[0].message.content.strip()
    json_text = _extract_json_from_text(raw)
    questions = _parse_questions_json(json_text)
    
    return questions[:question_count]


# ==================== OpenAI ====================

def generate_quiz_openai(content: str, question_count: int, difficulty: str, language: str, question_types: list, key_info: tuple) -> list:
    """توليد باستخدام OpenAI"""
    api_key, key_id = key_info
    
    client = OpenAI(api_key=api_key)
    prompt = _build_prompt(content, question_count, difficulty, language, question_types)
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096
    )
    
    raw = response.choices[0].message.content.strip()
    json_text = _extract_json_from_text(raw)
    questions = _parse_questions_json(json_text)
    
    return questions[:question_count]


# ==================== البدائل المجانية تماماً (بدون مفاتيح) ====================

def generate_quiz_simple(content: str, question_count: int, difficulty: str, language: str, question_types: list) -> list:
    """توليد أسئلة بسيطة بدون API - تعمل 100% حتى بدون مفاتيح"""
    logger.info("Using simple quiz generator (no API required)")
    
    sentences = content.split('。' if language == 'ar' else '.')
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        sentences = [content[:200]]
    
    questions = []
    types_available = [t for t in question_types if t in ['multiple_choice', 'true_false']]
    if not types_available:
        types_available = ['multiple_choice']
    
    for i in range(min(question_count, len(sentences) * 2)):
        sentence = sentences[i % len(sentences)]
        q_type = random.choice(types_available)
        
        if q_type == 'multiple_choice':
            # استخراج كلمات مفتاحية
            words = sentence.split()
            if len(words) > 5:
                key_word = words[len(words)//2]
                # خيارات عشوائية
                options = [
                    f"A) {key_word}",
                    f"B) {key_word} (غير صحيح)" if language == 'ar' else f"B) Not {key_word}",
                    f"C) {key_word} جزئياً" if language == 'ar' else f"C) Partially {key_word}",
                    f"D) لا شيء مما سبق" if language == 'ar' else "D) None of the above"
                ]
                correct = options[0]
                
                if language == 'ar':
                    question = f"ما هو الموضوع الرئيسي في: \"{sentence[:100]}...\"؟"
                    explanation = f"الموضوع الرئيسي هو {key_word} كما ورد في النص."
                else:
                    question = f"What is the main topic of: \"{sentence[:100]}...\"?"
                    explanation = f"The main topic is {key_word} as mentioned in the text."
                
                questions.append({
                    'type': 'multiple_choice',
                    'question': question,
                    'options': options,
                    'correct_answer': correct,
                    'explanation': explanation
                })
        
        elif q_type == 'true_false':
            # سؤال صح/خطأ
            is_true = random.choice([True, False])
            if language == 'ar':
                question = f"هل العبارة التالية صحيحة؟\n\"{sentence[:100]}...\""
                correct = "صحيح" if is_true else "خطأ"
                explanation = f"العبارة {'صحيحة' if is_true else 'خاطئة'} بناءً على النص المقدم."
            else:
                question = f"Is the following statement true?\n\"{sentence[:100]}...\""
                correct = "True" if is_true else "False"
                explanation = f"The statement is {'true' if is_true else 'false'} based on the provided text."
            
            questions.append({
                'type': 'true_false',
                'question': question,
                'options': None,
                'correct_answer': correct,
                'explanation': explanation
            })
    
    if not questions:
        # أسئلة افتراضية
        if language == 'ar':
            questions = [{
                'type': 'multiple_choice',
                'question': f'ماذا يتحدث النص عن: "{content[:100]}..."؟',
                'options': ['A) الموضوع الرئيسي', 'B) فكرة ثانوية', 'C) مثال توضيحي', 'D) مقدمة'],
                'correct_answer': 'A) الموضوع الرئيسي',
                'explanation': 'هذا هو السؤال الأول في الاختبار.'
            }]
        else:
            questions = [{
                'type': 'multiple_choice',
                'question': f'What is the text about: "{content[:100]}..."?',
                'options': ['A) Main topic', 'B) Secondary idea', 'C) Example', 'D) Introduction'],
                'correct_answer': 'A) Main topic',
                'explanation': 'This is the first question of the quiz.'
            }]
    
    return questions[:question_count]


def generate_quiz_huggingface_free(content: str, question_count: int, difficulty: str, language: str, question_types: list) -> list:
    """توليد أسئلة باستخدام HuggingFace API مجاني (بدون مفتاح)"""
    logger.info("Using HuggingFace free API (no key required)")
    
    if not REQUESTS_AVAILABLE:
        return generate_quiz_simple(content, question_count, difficulty, language, question_types)
    
    try:
        # استخدام API مجاني من HuggingFace
        prompt = _build_prompt(content, min(question_count, 10), difficulty, language, question_types)
        
        # محاولة استخدام نموذج مجاني
        api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
        
        response = requests.post(
            api_url,
            json={"inputs": prompt, "parameters": {"max_new_tokens": 2000, "temperature": 0.7}},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                raw = result[0].get('generated_text', '')
                json_text = _extract_json_from_text(raw)
                questions = _parse_questions_json(json_text)
                if questions:
                    return questions[:question_count]
    
    except Exception as e:
        logger.warning(f"HuggingFace free API failed: {e}")
    
    # في حال الفشل، استخدم المولد البسيط
    return generate_quiz_simple(content, question_count, difficulty, language, question_types)


# ==================== الوظيفة الرئيسية مع التبديل التلقائي ====================

def generate_quiz(content: str, question_count: int, difficulty: str, language: str, question_types: list = None) -> list:
    """توليد الأسئلة مع التبديل التلقائي بين جميع الخدمات والبدائل المجانية"""
    
    if not question_types:
        question_types = ['multiple_choice', 'true_false', 'fill_blank', 'qa']
    
    # ترتيب الخدمات حسب الأفضلية (المجانية أولاً)
    services = [
        # الطبقة 1: Groq (مجاني وسريع)
        ('groq', generate_quiz_groq, GROQ_AVAILABLE and key_manager.has_working_keys('groq')),
        # الطبقة 2: Gemini (مجاني)
        ('gemini', generate_quiz_gemini, GEMINI_AVAILABLE and key_manager.has_working_keys('gemini')),
        # الطبقة 3: DeepSeek (مدفوع)
        ('deepseek', generate_quiz_deepseek, key_manager.has_working_keys('deepseek')),
        # الطبقة 4: OpenRouter (مدفوع)
        ('openrouter', generate_quiz_openrouter, key_manager.has_working_keys('openrouter')),
        # الطبقة 5: OpenAI (مدفوع)
        ('openai', generate_quiz_openai, OPENAI_AVAILABLE and key_manager.has_working_keys('openai')),
    ]
    
    last_error = None
    
    # جرب جميع الخدمات التي لديها مفاتيح
    for service_name, func, is_available in services:
        if not is_available:
            continue
        
        max_attempts = len(key_manager.keys.get(service_name, [])) or 3
        for attempt in range(max_attempts):
            key_info = key_manager.get_next_key(service_name)
            if not key_info:
                break
            
            api_key, key_id = key_info
            
            try:
                logger.info(f"🔄 Trying {service_name}: {key_id}")
                result = func(content, question_count, difficulty, language, question_types, (api_key, key_id))
                key_manager.mark_key_success(service_name, key_id)
                logger.info(f"✅ Success with {service_name}: {key_id}")
                return result
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"❌ Failed {service_name}: {key_id} - {error_msg[:100]}")
                key_manager.mark_key_error(service_name, key_id, error_msg)
                last_error = e
                continue
    
    # الطبقة الأخيرة: البدائل المجانية تماماً (بدون مفاتيح)
    logger.info("🔄 All API keys exhausted, trying free fallback generators...")
    
    free_fallbacks = [
        ('HuggingFace Free API', generate_quiz_huggingface_free),
        ('Simple Quiz Generator', generate_quiz_simple),
    ]
    
    for name, func in free_fallbacks:
        try:
            logger.info(f"🔄 Trying {name}...")
            result = func(content, question_count, difficulty, language, question_types)
            if result:
                logger.info(f"✅ Success with {name}")
                return result
        except Exception as e:
            logger.warning(f"❌ {name} failed: {e}")
            continue
    
    # إذا وصلنا هنا، كل شيء فشل
    raise ValueError(
        f"All quiz generation methods failed! Last error: {last_error}\n\n"
        f"The bot will still work using the simple quiz generator.\n"
        f"Key Statistics:\n{key_manager.get_stats()}"
    )


def extract_topic_from_content(content: str, language: str = 'en') -> str:
    """استخراج الموضوع الرئيسي"""
    try:
        first_line = content.strip().split('\n')[0][:60]
        return first_line if first_line else "General Topic"
    except:
        return "General Topic"


def search_youtube(topic: str, language: str = 'en') -> list:
    """البحث عن مقاطع يوتيوب"""
    import urllib.parse
    
    if language == 'ar':
        queries = [f"{topic} شرح", f"{topic} درس"]
    else:
        queries = [f"{topic} tutorial", f"{topic} explanation"]
    
    videos = []
    for q in queries[:2]:
        encoded = urllib.parse.quote(q)
        videos.append({
            "title": q,
            "url": f"https://www.youtube.com/results?search_query={encoded}"
        })
    
    return videos


def evaluate_qa_answer(question: str, correct_answer: str, user_answer: str, language: str = 'en') -> dict:
    """تقييم إجابة السؤال المفتوح (بدون AI)"""
    user_lower = user_answer.lower().strip()
    correct_lower = correct_answer.lower().strip()
    
    if user_lower == correct_lower:
        score = 100
        feedback = "إجابة ممتازة!" if language == 'ar' else "Excellent answer!"
    elif correct_lower in user_lower or user_lower in correct_lower:
        score = 70
        feedback = "إجابة جيدة، قريبة من الصواب." if language == 'ar' else "Good answer, close to correct."
    elif len(user_lower) > len(correct_lower) * 0.5:
        score = 40
        feedback = "الإجابة غير مكتملة." if language == 'ar' else "Incomplete answer."
    else:
        score = 20
        feedback = "إجابة غير صحيحة." if language == 'ar' else "Incorrect answer."
    
    return {"score": score, "feedback": feedback}
