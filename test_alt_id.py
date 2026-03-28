import asyncio
from parser import ParserService
import json

async def test_alt_id():
    ps = ParserService()
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    # Alternative ID from handshake
    alt_id = "2833290" 
    date = "2026-03-18"
    
    url = f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?person_ids={alt_id}&begin_date={date}&end_date={date}&expand=homework,marks&source_types=PLAN,AE,EC,EVENTS"
    
    session = await ps._get_session()
    headers = ps.base_headers.copy()
    headers.update({
        'Authorization': f'Bearer {token}',
        'X-Mes-Subsystem': 'familyweb',
        'X-Mes-Role': 'student',
        'profile-id': alt_id
    })
    
    await ps._activate_session(token, subsystem='familyweb')
    
    async with session.get(url, headers=headers) as resp:
        print(f"Status: {resp.status}")
        data = await resp.json()
        items = data.get('response') or []
        print(f"Items found with ALT_ID ({alt_id}): {len(items)}")
        for it in items[:5]:
            print(f"  - {it.get('subject_name')} (Source: {it.get('source')})")

if __name__ == "__main__":
    asyncio.run(test_alt_id())
