import sqlite3
import json

conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute("SELECT user_id, first_name, token_mos, student_id, mesh_id FROM users LIMIT 5")
users = cursor.fetchall()
for u in users:
    print(f"User: {u[1]} (ID: {u[0]})")
    print(f"Token: {u[2]}")
    print(f"Student ID: {u[3]}")
    print(f"Mesh ID: {u[4]}")
    print("-" * 20)
conn.close()
