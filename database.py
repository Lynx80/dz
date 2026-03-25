import sqlite3
import logging

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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    grade TEXT,
                    token_mos TEXT,
                    token_mo TEXT,
                    student_id TEXT,
                    tests_solved INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0,
                    speed TEXT DEFAULT 'normal',
                    ai_enabled INTEGER DEFAULT 1
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    test_url TEXT,
                    score TEXT,
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

    def create_user(self, user_id, first_name=None, last_name=None, grade=None, student_id=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, grade, student_id)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, first_name, last_name, grade, student_id))
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

    def add_test_score(self, user_id, test_url, score_str):
        # score_str example: "8/10" or "85%"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Добавляем в историю
            cursor.execute("""
                INSERT INTO tests (user_id, test_url, score)
                VALUES (?, ?, ?)
            """, (user_id, test_url, score_str))
            
            # Обновляем статистику пользователя
            cursor.execute("SELECT tests_solved, avg_score FROM users WHERE user_id = ?", (user_id,))
            solved, current_avg = cursor.fetchone()
            
            # Парсим числовое значение из score_str для расчета среднего если возможно
            try:
                if "/" in score_str:
                    num, den = map(float, score_str.split("/"))
                    numeric_score = (num / den) * 100
                elif "%" in score_str:
                    numeric_score = float(score_str.replace("%", ""))
                else:
                    numeric_score = float(score_str)
                
                new_avg = (current_avg * solved + numeric_score) / (solved + 1)
            except:
                new_avg = current_avg

            cursor.execute("""
                UPDATE users 
                SET tests_solved = tests_solved + 1, 
                    avg_score = ?
                WHERE user_id = ?
            """, (new_avg, user_id))
            conn.commit()

    def get_user_tests(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT test_url, score, timestamp FROM tests WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
            return cursor.fetchall()
