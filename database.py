import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

_raw_url = os.environ.get("DATABASE_URL", "")
DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1) if _raw_url.startswith("postgres://") else _raw_url


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                attempts INTEGER DEFAULT 3,
                points FLOAT DEFAULT 0,
                total_quizzes INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by BIGINT,
                invited_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                is_banned BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                title TEXT,
                content TEXT,
                language TEXT DEFAULT 'en',
                difficulty TEXT DEFAULT 'medium',
                question_count INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
                question_type TEXT NOT NULL,
                question_text TEXT NOT NULL,
                options JSONB,
                correct_answer TEXT NOT NULL,
                explanation TEXT,
                question_order INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                quiz_id INTEGER REFERENCES quizzes(id),
                score INTEGER DEFAULT 0,
                total_questions INTEGER DEFAULT 0,
                answers JSONB,
                started_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                is_completed BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount INTEGER,
                payment_type TEXT,
                attempts_added INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT REFERENCES users(user_id),
                referred_id BIGINT REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(referred_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS point_transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount FLOAT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE users ALTER COLUMN points SET DEFAULT 3")
        cur.execute("UPDATE users SET points = 3 WHERE points = 0")
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"Database init error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def get_user(user_id: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None


def create_user(user_id: int, username: str, first_name: str, last_name: str, referral_code: str, referred_by: int = None):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, referral_code, referred_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
                RETURNING *
            """, (user_id, username or '', first_name or '', last_name or '', referral_code, referred_by))
            conn.commit()
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"create_user error: {e}")
        return None


def update_user_attempts(user_id: int, delta: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE users SET attempts = GREATEST(0, attempts + %s)
                WHERE user_id = %s RETURNING attempts
            """, (delta, user_id))
            conn.commit()
            row = cur.fetchone()
            return row['attempts'] if row else None
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"update_user_attempts error: {e}")
        return None


def update_user_points(user_id: int, delta: float, description: str = None):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE users SET points = points + %s
                WHERE user_id = %s RETURNING points
            """, (delta, user_id))
            row = cur.fetchone()
            new_balance = row['points'] if row else None
            if new_balance is not None:
                cur.execute("""
                    INSERT INTO point_transactions (user_id, amount, description)
                    VALUES (%s, %s, %s)
                """, (user_id, delta, description or ('خصم' if delta < 0 else 'إضافة')))
            conn.commit()
            return new_balance
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"update_user_points error: {e}")
        return None


def get_point_transactions(user_id: int, limit: int = 10):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT amount, description, created_at
                FROM point_transactions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_point_transactions error: {e}")
        return []


def add_referral(referrer_id: int, referred_id: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (%s, %s)
                ON CONFLICT (referred_id) DO NOTHING
                RETURNING id
            """, (referrer_id, referred_id))
            row = cur.fetchone()
            conn.commit()

            if not row:
                return False, False, None

            cur.execute("""
                UPDATE users
                SET invited_count = invited_count + 1, points = points + 0.2
                WHERE user_id = %s
                RETURNING invited_count, points
            """, (referrer_id,))
            result = cur.fetchone()

            new_points = float(result['points']) if result else None

            cur.execute("""
                INSERT INTO point_transactions (user_id, amount, description)
                VALUES (%s, %s, %s)
            """, (referrer_id, 0.2, 'مكافأة دعوة صديق'))
            conn.commit()

            got_bonus = False
            if result and result['invited_count'] % 5 == 0:
                cur.execute("UPDATE users SET attempts = attempts + 1 WHERE user_id = %s", (referrer_id,))
                conn.commit()
                got_bonus = True

            return True, got_bonus, new_points
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"add_referral error: {e}")
        return False, False, None


def save_quiz(user_id: int, title: str, content: str, language: str, difficulty: str, question_count: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO quizzes (user_id, title, content, language, difficulty, question_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (user_id, title[:200] if title else 'Quiz', content[:8000] if content else '', language, difficulty, question_count))
            conn.commit()
            row = cur.fetchone()
            return row['id'] if row else None
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"save_quiz error: {e}")
        return None


def save_questions(quiz_id: int, questions: list):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            for i, q in enumerate(questions):
                options_val = q.get('options')
                cur.execute("""
                    INSERT INTO questions
                        (quiz_id, question_type, question_text, options,
                         correct_answer, explanation, question_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    quiz_id,
                    q.get('type', 'multiple_choice'),
                    q.get('question', ''),
                    json.dumps(options_val) if options_val else None,
                    q.get('correct_answer', ''),
                    q.get('explanation', ''),
                    i + 1
                ))
            conn.commit()
            return True
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"save_questions error: {e}")
        return False


def get_quiz_questions(quiz_id: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM questions WHERE quiz_id = %s ORDER BY question_order", (quiz_id,))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_quiz_questions error: {e}")
        return []


def save_quiz_attempt(user_id: int, quiz_id: int, score: int, total: int, answers: list):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO quiz_attempts
                    (user_id, quiz_id, score, total_questions, answers, completed_at, is_completed)
                VALUES (%s, %s, %s, %s, %s, NOW(), TRUE)
                RETURNING id
            """, (user_id, quiz_id, score, total, json.dumps(answers, ensure_ascii=False)))
            attempt_row = cur.fetchone()

            cur.execute("UPDATE users SET total_quizzes = total_quizzes + 1 WHERE user_id = %s", (user_id,))
            conn.commit()
            return attempt_row['id'] if attempt_row else None
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"save_quiz_attempt error: {e}")
        return None


def get_stats():
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) as total_users FROM users")
            r1 = cur.fetchone()
            cur.execute("SELECT COUNT(*) as total_quizzes FROM quizzes")
            r2 = cur.fetchone()
            cur.execute("SELECT COUNT(*) as total_attempts FROM quiz_attempts WHERE is_completed = TRUE")
            r3 = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(attempts), 0) as total_attempts_left FROM users")
            r4 = cur.fetchone()
            return {
                'total_users': r1['total_users'] if r1 else 0,
                'total_quizzes': r2['total_quizzes'] if r2 else 0,
                'total_attempts': r3['total_attempts'] if r3 else 0,
                'total_attempts_left': r4['total_attempts_left'] if r4 else 0,
            }
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return {'total_users': 0, 'total_quizzes': 0, 'total_attempts': 0, 'total_attempts_left': 0}


def get_all_users(limit: int = 20, offset: int = 0):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT user_id, username, first_name, attempts, points, total_quizzes, created_at, is_banned
                FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (limit, offset))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_all_users error: {e}")
        return []


def ban_user(user_id: int, banned: bool):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET is_banned = %s WHERE user_id = %s RETURNING user_id", (banned, user_id))
            conn.commit()
            row = cur.fetchone()
            return row is not None
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"ban_user error: {e}")
        return False


def add_payment(user_id: int, amount: int, payment_type: str, attempts_added: int, status: str = 'confirmed'):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO payments (user_id, amount, payment_type, attempts_added, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, amount, payment_type, attempts_added, status))
            if status == 'confirmed' and attempts_added > 0:
                cur.execute("UPDATE users SET attempts = attempts + %s WHERE user_id = %s", (attempts_added, user_id))
            conn.commit()
            return True
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"add_payment error: {e}")
        return False


def set_user_attempts(user_id: int, amount: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET attempts = %s WHERE user_id = %s RETURNING attempts", (amount, user_id))
            conn.commit()
            row = cur.fetchone()
            return row['attempts'] if row else None
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"set_user_attempts error: {e}")
        return None


def get_user_by_username(username: str):
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            uname = username.lstrip('@')
            cur.execute("SELECT * FROM users WHERE username = %s", (uname,))
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"get_user_by_username error: {e}")
        return None
