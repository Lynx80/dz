import asyncio
import json
import logging
from parser import ParserService

async def debug_one_api():
    # Fresh token from DB
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    student_id = "2584884"
    date = "2026-03-18"
    
    parser = ParserService()
    session = await parser._get_session()
    
    headers = parser.base_headers.copy()
    headers['Authorization'] = f'Bearer {token}'
    headers['auth-token'] = token
    headers['X-Mes-Subsystem'] = 'familymp'
    headers['X-Mes-Role'] = 'student'
    
    # Handshake
    await parser._activate_session(token, subsystem='familymp')
    
    # Try V2 Diary - it's often the richest
    url = f"https://api.myschool.mosreg.ru/family/v2/diary?student_id={student_id}&date={date}&expand=homework,entries,materials,details"
    
    async with session.get(url, headers=headers) as resp:
        print(f"Status: {resp.status}")
        if resp.status == 200:
            data = await resp.json()
            with open('debug_raw_v2_diary.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("Dumped to debug_raw_v2_diary.json")
        else:
            print(await resp.text())
    
    await session.close()

if __name__ == "__main__":
    asyncio.run(debug_one_api())
