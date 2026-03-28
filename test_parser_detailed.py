import asyncio
import logging
from parser import ParserService

# Configure logging to see the output from parser.py
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

async def test_refactored_parser():
    # Fresh token from DB
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    student_id = "2584884"
    mesh_id = "7c0be908-fe90-4a99-83ed-aec4ece7948d"
    date = "2026-03-18" 
    
    parser = ParserService()
    try:
        print(f"--- FETCHING SCHEDULE FOR {date} ---")
        lessons = await parser.get_mosreg_schedule(token, student_id, date, mesh_id=mesh_id)
        if lessons:
            print(f"Success! Found {len(lessons)} lessons.")
            for i, l in enumerate(lessons, 1):
                print(f"{i}. {l['time']} {l['subject']}")
                if l['materials']:
                    print(f"   [MATERIALS]: {len(l['materials'])} items")
                    for m in l['materials']:
                        print(f"     - {m['title']}: {m['link']}")
        else:
            print("No lessons found or error occurred.")
    finally:
        await (await parser._get_session()).close()

if __name__ == "__main__":
    asyncio.run(test_refactored_parser())
