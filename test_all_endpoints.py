import asyncio
from parser import ParserService
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test_all_endpoints():
    ps = ParserService()
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    student_id = "2584884"
    date = "2026-03-18" 
    mesh_id = "2833290"
    
    await ps.fetch_mosreg_profile(token)
    
    endpoints = [
        ("https://authedu.mosreg.ru/api/eventcalendar/v1/api/events", "familyweb", "person_ids", True),
        ("https://api.myschool.mosreg.ru/family/mobile/v1/schedule/short", "familymp", "student_id", False),
        ("https://api.myschool.mosreg.ru/family/mobile/v1/profile/current/schedule", "familymp", "date", False),
        ("https://api.myschool.mosreg.ru/family/v2/diary", "familymp", "student_id", False),
    ]
    
    session = await ps._get_session()
    
    for url_base, sub, id_param, use_guid in endpoints:
        print(f"\n--- Testing {sub} ({url_base}) ---")
        cur_id = student_id if not use_guid else student_id # Try student_id first
        
        if "eventcalendar" in url_base:
            url = f"{url_base}?person_ids={cur_id}&begin_date={date}&end_date={date}&expand=homework,marks&source_types=PLAN,AE,EC"
        elif "short" in url_base:
            url = f"{url_base}?student_id={cur_id}&from={date}&to={date}&expand=homework,entries,materials"
        elif "profile/current" in url_base:
            url = f"{url_base}?date={date}"
        else:
            url = f"{url_base}?student_id={cur_id}&date={date}&expand=homework"

        headers = ps.base_headers.copy()
        headers.update({
            'Authorization': f'Bearer {token}',
            'X-Mes-Subsystem': sub,
            'X-Mes-Role': 'student',
            'profile-id': '2833290',
            'profile-type': 'student'
        })
        
        await ps._activate_session(token, subsystem=sub)
        
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get('response') or data.get('data') or data.get('payload') or []
                    if not items and isinstance(data, list): items = data
                    print(f"Found {len(items)} items")
                    for it in items[:2]:
                        subj = it.get('subject_name') or it.get('title')
                        source = it.get('source')
                        print(f"  - {subj} (Source: {source})")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
