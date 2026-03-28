import aiohttp
import asyncio
import json

async def test_v3():
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
    student_id = "2584884"
    date = "2026-03-27"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Mes-Subsystem": "familymp",
        "X-Mes-Role": "student",
        "Accept": "application/json",
        "Referer": "https://myschool.mosreg.ru/",
        "Cookie": f"identity={token}"
    }
    
    async with aiohttp.ClientSession() as session:
        # Handshake
        await session.get("https://myschool.mosreg.ru/acl/api/users/profile_info", headers=headers)
        
        url = f"https://api.myschool.mosreg.ru/family/mobile/v1/schedule/short?student_id={student_id}&from={date}&to={date}&expand=homework,materials,entries,details"
        print(f"Testing API with Cookie: {url}")
        
        async with session.get(url, headers=headers) as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"Data keys: {data.keys()}")
                if 'data' in data and 'items' in data['data']:
                    items = data['data']['items']
                    print(f"Items found: {len(items)}")
                    if items:
                        # Inspect the first item for homework structure
                        item = items[0]
                        print(f"Sample Item Keys: {item.keys()}")
                        if 'homework' in item:
                            print(f"Homework Keys: {item['homework'].keys() if item['homework'] else 'None'}")
                        # Look for materials/entries
                        if 'materials' in item: print(f"Materials: {item['materials']}")
                        
                with open('debug_raw_v3.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                print(f"Error: {await resp.text()}")

if __name__ == "__main__":
    asyncio.run(test_v3())
