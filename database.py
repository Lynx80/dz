import sqlite3
import logging
import json

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        self._create_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Таблица пользователей с расширенными настройками
            cursor.execute("""
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
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'mesh_id' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN mesh_id TEXT")
                logger.info("Database migration: added mesh_id column to users table")
            
            # Таблица кеша ответов ИИ
            # ...
            # Таблица кеша ответов ИИ (для экономии токенов)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_cache (
                    question_hash TEXT PRIMARY KEY,
                    question_text TEXT,
                    options_json TEXT,
                    answer_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # История решений и статистика
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stats_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subject TEXT,
                    task_type TEXT,
                    success INTEGER,
                    tokens_saved INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            conn.commit()

    def get_user(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None

    def create_user(self, user_id, first_name=None, last_name=None, grade=None, student_id=None, mesh_id=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, grade, student_id, mesh_id, solve_delay, accuracy_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, first_name, last_name, grade, student_id, mesh_id, 15, 'advanced'))
            conn.commit()

    def update_user(self, user_id, **kwargs):
        if not kwargs:
            return
        keys = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {keys} WHERE user_id = ?", values)
            conn.commit()

    def delete_user(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_answer_cache(self, question_text, options):
        import hashlib
        options_json = json.dumps(options, sort_keys=True)
        q_hash = hashlib.sha256(f"{question_text}{options_json}".encode()).hexdigest()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT answer_text FROM ai_cache WHERE question_hash = ?", (q_hash,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_answer_cache(self, question_text, options, answer_text):
        import hashlib
        options_json = json.dumps(options, sort_keys=True)
        q_hash = hashlib.sha256(f"{question_text}{options_json}".encode()).hexdigest()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ai_cache (question_hash, question_text, options_json, answer_text)
                VALUES (?, ?, ?, ?)
            """, (q_hash, question_text, options_json, answer_text))
            conn.commit()

    def get_stats(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tests_solved, avg_score FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row: return {"solved": 0, "avg": 0, "saved": 0}
            
            cursor.execute("SELECT SUM(tokens_saved) FROM stats_history WHERE user_id = ?", (user_id,))
            saved = cursor.fetchone()[0] or 0
            return {"solved": row[0], "avg": round(row[1], 1), "saved": saved}

    def add_stats(self, user_id, subject, task_type, success=1, tokens_saved=0):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stats_history (user_id, subject, task_type, success, tokens_saved)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, subject, task_type, success, tokens_saved))
            conn.commit()

    def add_test_score(self, user_id, test_url, score_str):
        # Сохраняем в историю и обновляем агрегаты
        with self._get_connection() as conn:
            cursor = conn.cursor()
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

            cursor.execute("SELECT tests_solved, avg_score FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            solved, current_avg = row if row else (0, 0)
            
            new_avg = (current_avg * solved + numeric_score) / (solved + 1)
            
            cursor.execute("""
                UPDATE users 
                SET tests_solved = tests_solved + 1, avg_score = ?
                WHERE user_id = ?
            """, (new_avg, user_id))
            
            # Вставляем статистику напрямую, чтобы избежать вложенного соединения
            cursor.execute("""
                INSERT INTO stats_history (user_id, subject, task_type, success, tokens_saved)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, "Тест", "auto_solve", 1, 500))
            conn.commit()

    def get_all_users_with_tokens(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, token_mos FROM users WHERE token_mos IS NOT NULL")
            rows = cursor.fetchall()
            return [{"user_id": r[0], "token_mos": r[1]} for r in rows]
