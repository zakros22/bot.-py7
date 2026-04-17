import os
import re
import json
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

_openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
_openai_base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

client = OpenAI(
    api_key=_openai_key,
    **( {"base_url": _openai_base} if _openai_base else {} )
)


def detect_language(text: str) -> str:
    """كشف اللغة (عربية أو إنجليزية)"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return 'en'
    return 'ar' if (arabic_chars / total_chars) > 0.25 else 'en'


def _extract_json_from_text(raw: str) -> str:
    """استخراج JSON من النص الخام"""
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
        questions = json.loads(fixed)

    if not isinstance(questions, list):
        raise ValueError(f"Expected JSON array, got {type(questions).__name__}")

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


ALL_TYPES = ['multiple_choice', 'true_false', 'fill_blank', 'qa']


def generate_quiz(content: str, question_count: int, difficulty: str, language: str, question_types: list = None) -> list:
    """توليد أسئلة اختبار باستخدام OpenAI"""
    if not content or len(content.strip()) < 10:
        raise ValueError("Content is too short to generate a quiz")

    if not question_types:
        question_types = ALL_TYPES
    question_types = [t for t in question_types if t in ALL_TYPES]
    if not question_types:
        question_types = ALL_TYPES

    diff_map = {
        'easy': 'simple and straightforward, suitable for beginners',
        'medium': 'moderately challenging, tests good understanding',
        'hard': 'difficult and thought-provoking, tests deep knowledge',
    }
    diff_desc = diff_map.get(difficulty, 'moderately challenging')

    if language == 'ar':
        lang_instruction = "CRITICAL: Write ALL questions, options, answers, and explanations in Arabic. Do not use any English except for proper nouns."
        tf_values = '"صحيح" أو "خطأ"'
    else:
        lang_instruction = "Write all questions, options, answers, and explanations in English."
        tf_values = '"True" or "False"'

    content_snippet = content[:4500]

    type_lines = []
    type_names = []
    if 'multiple_choice' in question_types:
        type_lines.append('- multiple_choice  — 4 options labeled "A) ...", "B) ...", "C) ...", "D) ..."')
        type_names.append('multiple_choice')
    if 'true_false' in question_types:
        type_lines.append(f'- true_false       — answer is exactly {tf_values}')
        type_names.append('true_false')
    if 'fill_blank' in question_types:
        type_lines.append('- fill_blank       — sentence with ___ ; answer is the missing word/phrase')
        type_names.append('fill_blank')
    if 'qa' in question_types:
        type_lines.append('- qa               — open-ended question with a full model answer')
        type_names.append('qa')

    types_str = '\n'.join(type_lines)
    allowed_types_json = ' | '.join(f'"{t}"' for t in type_names)

    per_type = max(1, question_count // len(question_types))
    dist_parts = [f'{per_type} {t}' for t in type_names]
    dist_hint = ', '.join(dist_parts)

    prompt = f"""You are an expert educational quiz generator.
Read the content below and create exactly {question_count} quiz questions.

{lang_instruction}
Difficulty: {diff_desc}

ALLOWED QUESTION TYPES (use ONLY these):
{types_str}

CONTENT:
---
{content_snippet}
---

Return ONLY a valid JSON array. Each item:
{{
  "type": {allowed_types_json},
  "question": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."] or null,
  "correct_answer": "...",
  "explanation": "..."
}}

Target distribution: {dist_hint} (spread evenly across allowed types).
Total: exactly {question_count} questions.
Return ONLY the JSON array, nothing else."""

    system_msg = "You are an expert quiz generator. Always respond with a single valid JSON array. No prose, no markdown fences, no comments outside the array."

    last_error = None
    raw = ''

    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(1)

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ]
            )

            raw = (response.choices[0].message.content or '').strip()
            if not raw:
                last_error = ValueError("AI returned an empty response")
                continue

            json_text = _extract_json_from_text(raw)
            valid = _parse_questions_json(json_text)

            if not valid:
                last_error = ValueError("No valid questions in AI response")
                continue

            logger.info(f"generate_quiz: {len(valid)} valid questions (requested {question_count})")
            return valid[:question_count]

        except json.JSONDecodeError as e:
            logger.error(f"generate_quiz attempt {attempt + 1} JSON error: {e}")
            last_error = ValueError("AI returned invalid JSON")
        except Exception as e:
            logger.error(f"generate_quiz attempt {attempt + 1} error: {e}")
            last_error = e

    raise last_error or ValueError("Failed to generate quiz after 3 attempts.")


def search_youtube(topic: str, language: str = 'en') -> list:
    """البحث عن مقاطع يوتيوب"""
    try:
        import urllib.parse
        videos = []
        
        if language == 'ar':
            queries = [f"{topic} شرح", f"{topic} درس"]
        else:
            queries = [f"{topic} tutorial", f"{topic} explanation"]
        
        for q in queries[:2]:
            encoded = urllib.parse.quote(q)
            videos.append({
                "title": q,
                "url": f"https://www.youtube.com/results?search_query={encoded}"
            })
        
        return videos
    except Exception as e:
        logger.error(f"search_youtube error: {e}")
        return []


def extract_topic_from_content(content: str, language: str = 'en') -> str:
    """استخراج الموضوع الرئيسي من المحتوى"""
    try:
        snippet = content[:600].strip()
        if not snippet:
            return "General Topic"
        
        if language == 'ar':
            prompt = f"في 3 كلمات أو أقل، ما هو الموضوع الرئيسي لهذا النص؟ أجب بالعربية فقط:\n\n{snippet}"
        else:
            prompt = f"In 3 words or less, what is the main topic of this text? Reply only with the topic:\n\n{snippet}"
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = (response.choices[0].message.content or '').strip()
        topic = raw.strip('"\'.,،:')
        return topic if topic else snippet[:40]
    except Exception as e:
        logger.error(f"extract_topic error: {e}")
        first_line = content.strip().split('\n')[0][:60]
        return first_line if first_line else "General Topic"


def evaluate_qa_answer(question: str, correct_answer: str, user_answer: str, language: str = 'en') -> dict:
    """تقييم إجابة السؤال المفتوح"""
    try:
        if not user_answer or len(user_answer.strip()) < 2:
            return {"score": 0, "feedback": "لم تكتب إجابة." if language == 'ar' else "No answer provided."}
        
        if language == 'ar':
            prompt = (f"قيّم إجابة الطالب من 0 إلى 100:\n\n"
                      f"السؤال: {question}\n"
                      f"الإجابة النموذجية: {correct_answer}\n"
                      f"إجابة الطالب: {user_answer}\n\n"
                      f'أرجع JSON فقط: {{"score": <0-100>, "feedback": "<تقييم موجز بالعربية>"}}')
        else:
            prompt = (f"Evaluate this student answer (0-100):\n\n"
                      f"Question: {question}\n"
                      f"Model Answer: {correct_answer}\n"
                      f"Student Answer: {user_answer}\n\n"
                      f'Return ONLY JSON: {{"score": <0-100>, "feedback": "<brief evaluation>"}}')
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = (response.choices[0].message.content or '').strip()
        json_text = _extract_json_from_text(raw)
        result = json.loads(json_text)
        score = max(0, min(100, int(result.get('score', 50))))
        feedback = str(result.get('feedback', ''))
        return {"score": score, "feedback": feedback}
    except Exception as e:
        logger.error(f"evaluate_qa_answer error: {e}")
        return {"score": 50, "feedback": "تعذّر التقييم التلقائي." if language == 'ar' else "Could not evaluate automatically."}
