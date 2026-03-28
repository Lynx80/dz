import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute("SELECT user_id, first_name, token_mos, student_id, mesh_id FROM users")
users = cursor.fetchall()
for u in users:
    has_token = "YES" if u[2] else "NO"
    print(f"ID: {u[0]} | Name: {u[1]} | Token: {has_token} | SID: {u[3]}")
conn.close()
