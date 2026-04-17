import os
import re
import json
import logging
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
            continue
        q.setdefault('explanation', '')
        valid.append(q)
    
    return valid


def _build_prompt(content: str, question_count: int, difficulty: str, language: str, question_types: list) -> str:
    """بناء النص الموجه"""
    diff_map = {
        'easy': 'سهلة وبسيطة' if language == 'ar' else 'easy',
        'medium': 'متوسطة الصعوبة' if language == 'ar' else 'medium',
        'hard': 'صعبة ومتطلبة' if language == 'ar' else 'hard'
    }
    
    type_names = {
        'multiple_choice': 'اختيار متعدد' if language == 'ar' else 'Multiple Choice',
        'true_false': 'صح/خطأ' if language == 'ar' else 'True/False',
        'fill_blank': 'ملء الفراغات' if language == 'ar' else 'Fill in Blank',
        'qa': 'سؤال وجواب' if language == 'ar' else 'Q&A'
    }
    
    types_list = ', '.join([type_names.get(t, t) for t in question_types])
    
    if language == 'ar':
        return f"""أنت خبير في إنشاء الاختبارات التعليمية.

المحتوى:
---
{content[:4000]}
---

الرجاء إنشاء {question_count} سؤال اختبار.
مستوى الصعوبة: {diff_map.get(difficulty, 'متوسطة')}
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
{content[:4000]}
---

Generate {question_count} quiz questions.
Difficulty: {diff_map.get(difficulty, 'medium')}
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


# ==================== Groq (Llama 3) ====================

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


# ==================== Gemini ====================

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
    
    if not questions:
        raise ValueError("No valid questions generated")
    
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
    
    if not questions:
        raise ValueError("No valid questions generated")
    
    return questions[:question_count]


# ==================== الوظيفة الرئيسية مع التبديل التلقائي ====================

def generate_quiz(content: str, question_count: int, difficulty: str, language: str, question_types: list = None) -> list:
    """توليد الأسئلة مع التبديل التلقائي بين جميع المفاتيح والخدمات"""
    
    if not question_types:
        question_types = ['multiple_choice', 'true_false', 'fill_blank', 'qa']
    
    # ترتيب الخدمات حسب الأفضلية
    services = [
        ('groq', generate_quiz_groq, GROQ_AVAILABLE),
        ('gemini', generate_quiz_gemini, GEMINI_AVAILABLE),
        ('deepseek', generate_quiz_deepseek, True),
        ('openrouter', generate_quiz_openrouter, True),
        ('openai', generate_quiz_openai, OPENAI_AVAILABLE),
    ]
    
    last_error = None
    
    for service_name, func, is_available in services:
        if not is_available:
            continue
        
        # جرب جميع مفاتيح هذه الخدمة
        for attempt in range(10):  # كحد أقصى 10 محاولات لكل خدمة
            key_info = key_manager.get_next_key(service_name)
            if not key_info:
                break  # لا يوجد مفاتيح متاحة لهذه الخدمة
            
            api_key, key_id = key_info
            
            try:
                logger.info(f"Attempting with {service_name}: {key_id} (attempt {attempt+1})")
                result = func(content, question_count, difficulty, language, question_types, (api_key, key_id))
                
                # نجاح - سجل النجاح
                key_manager.mark_key_success(service_name, key_id)
                logger.info(f"Success with {service_name}: {key_id}")
                return result
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Failed with {service_name}: {key_id} - {error_msg[:100]}")
                key_manager.mark_key_error(service_name, key_id, error_msg)
                last_error = e
                continue
    
    # إذا وصلنا هنا، كل المفاتيح فشلت
    raise ValueError(
        f"All API keys exhausted! Last error: {last_error}\n\n"
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
    """تقييم إجابة السؤال المفتوح"""
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
