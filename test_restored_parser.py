import asyncio
from parser import ParserService
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test_restored():
    ps = ParserService()
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    student_id = "2584884"
    date = "2026-03-18" 
    mesh_id = "2833290"
    
    # Force profile handshake
    await ps.fetch_mosreg_profile(token)
    
    # Manual call to eventcalendar to see EVERYTHING
    url = f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?person_ids={student_id}&begin_date={date}&end_date={date}&expand=homework,marks,absence_reason_id,health_status,nonattendance_reason_id&source_types=PLAN,AE,EC,EVENTS,AFISHA,ORGANIZER,OLYMPIAD,PROF"
    
    session = await ps._get_session()
    headers = ps.base_headers.copy()
    headers.update({
        'Authorization': f'Bearer {token}',
        'X-Mes-Subsystem': 'familyweb',
        'X-Mes-Role': 'student',
        'profile-id': '2833290',
        'Referer': 'https://authedu.mosreg.ru/diary/schedules/day/'
    })
    
    await ps._activate_session(token, subsystem='familyweb')
    
    async with session.get(url, headers=headers) as resp:
        print(f"Status: {resp.status}")
        data = await resp.json()
        with open('debug_restored_raw.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        items = data.get('response') or []
        print(f"Items in response: {len(items)}")
        for i, item in enumerate(items):
            print(f"{i+1}. {item.get('subject_name')} (Source: {item.get('source')})")

if __name__ == "__main__":
    asyncio.run(test_restored())
