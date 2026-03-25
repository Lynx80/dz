import aiosqlite
import os

DB_PATH = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                token TEXT,
                first_name TEXT,
                last_name TEXT,
                class_name TEXT,
                region TEXT
            )
        """)
        await db.commit()

async def get_user_token(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT token FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def save_user_token(user_id: int, token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, token) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET token = excluded.token
        """, (user_id, token))
        await db.commit()

async def update_user_profile(user_id: int, first_name: str, last_name: str, class_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET first_name = ?, last_name = ?, class_name = ?
            WHERE user_id = ?
        """, (first_name, last_name, class_name, user_id))
        await db.commit()

async def get_user_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()
