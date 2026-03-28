import aiosqlite
import logging
import json
import hashlib
from config import DB_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    async def _create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    grade TEXT,
                    token_mos TEXT,
                    student_id TEXT,
                    mesh_id TEXT,
                    tests_solved INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0,
                    mode TEXT DEFAULT 'fast',
                    api_limits INTEGER DEFAULT 100,
                    auto_solve INTEGER DEFAULT 0,
                    cache_enabled INTEGER DEFAULT 1,
                    logs_enabled INTEGER DEFAULT 1,
                    language TEXT DEFAULT 'ru',
                    solve_delay INTEGER DEFAULT 15,
                    accuracy_mode TEXT DEFAULT 'advanced'
                )
            """)
            
            # Миграция: Добавляем mesh_id если его нет
            cursor = await db.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in await cursor.fetchall()]
            if 'mesh_id' not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN mesh_id TEXT")
                logger.info("Database migration: added mesh_id column to users table")
            
            # Таблица кеша ответов ИИ
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_cache (
                    question_hash TEXT PRIMARY KEY,
                    question_text TEXT,
                    options_json TEXT,
                    answer_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица истории тестов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS test_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    test_url TEXT,
                    score TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица выполненных заданий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS completed_homework (
                    user_id INTEGER,
                    date_str TEXT,
                    hw_hash TEXT,
                    PRIMARY KEY (user_id, date_str, hw_hash)
                )
            """)
            
            # Таблица для хранения путей к профилям браузера
            await db.execute("""
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    user_id INTEGER PRIMARY KEY,
                    profile_path TEXT,
                    last_active DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица статистики (для полноты, если она используется)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stats_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subject TEXT,
                    task_type TEXT,
                    success INTEGER,
                    tokens_saved INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_user(self, user_id, first_name=None, last_name=None, grade=None, student_id=None, mesh_id=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, grade, student_id, mesh_id, solve_delay, accuracy_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, first_name, last_name, grade, student_id, mesh_id, 15, 'advanced'))
            await db.commit()

    async def update_user(self, user_id, **kwargs):
        if not kwargs:
            return
        keys = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE users SET {keys} WHERE user_id = ?", values)
            await db.commit()

    async def delete_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_answer_cache(self, question_text, options):
        options_json = json.dumps(options, sort_keys=True)
        q_hash = hashlib.sha256(f"{question_text}{options_json}".encode()).hexdigest()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT answer_text FROM ai_cache WHERE question_hash = ?", (q_hash,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_answer_cache(self, question_text, options, answer_text):
        options_json = json.dumps(options, sort_keys=True)
        q_hash = hashlib.sha256(f"{question_text}{options_json}".encode()).hexdigest()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO ai_cache (question_hash, question_text, options_json, answer_text)
                VALUES (?, ?, ?, ?)
            """, (q_hash, question_text, options_json, answer_text))
            await db.commit()

    async def get_stats(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT tests_solved, avg_score FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return {"solved": 0, "avg": 0, "saved": 0}
                
                solved, avg = row
                
                async with db.execute("SELECT SUM(tokens_saved) FROM stats_history WHERE user_id = ?", (user_id,)) as cursor2:
                    row2 = await cursor2.fetchone()
                    saved = row2[0] or 0
                    return {"solved": solved, "avg": round(avg, 1), "saved": saved}

    async def add_test_score(self, user_id, test_url, score_str):
        try:
            if "/" in score_str:
                num, den = map(float, score_str.split("/"))
                numeric_score = (num / den) * 100
            elif "%" in score_str:
                numeric_score = float(score_str.replace("%", ""))
            else:
                numeric_score = float(score_str)
        except:
            numeric_score = 0

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT tests_solved, avg_score FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                solved, current_avg = row if row else (0, 0)
                
                new_avg = (current_avg * solved + numeric_score) / (solved + 1)
                
                await db.execute("""
                    UPDATE users 
                    SET tests_solved = tests_solved + 1, avg_score = ?
                    WHERE user_id = ?
                """, (new_avg, user_id))
                
                await db.execute("""
                    INSERT INTO stats_history (user_id, subject, task_type, success, tokens_saved)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, "Тест", "auto_solve", 1, 500))
                await db.commit()

    async def mark_hw_completed(self, user_id, date_str, hw_hash):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR IGNORE INTO completed_homework (user_id, date_str, hw_hash)
                VALUES (?, ?, ?)
            """, (user_id, date_str, hw_hash))
            await db.commit()

    async def unmark_hw_completed(self, user_id, date_str, hw_hash):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                DELETE FROM completed_homework 
                WHERE user_id = ? AND date_str = ? AND hw_hash = ?
            """, (user_id, date_str, hw_hash))
            await db.commit()

    async def is_hw_completed(self, user_id, date_str, hw_hash):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 1 FROM completed_homework 
                WHERE user_id = ? AND date_str = ? AND hw_hash = ?
            """, (user_id, date_str, hw_hash)) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def add_test_history(self, user_id, test_url, score):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO test_history (user_id, test_url, score)
                VALUES (?, ?, ?)
            """, (user_id, test_url, score))
            await db.commit()

    async def get_browser_session(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT profile_path FROM browser_sessions WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_browser_session(self, user_id, profile_path):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO browser_sessions (user_id, profile_path, last_active)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (user_id, profile_path))
            await db.commit()

    async def get_all_users_with_tokens(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, token_mos FROM users WHERE token_mos IS NOT NULL") as cursor:
                rows = await cursor.fetchall()
                return [{"user_id": r[0], "token_mos": r[1]} for r in rows]
