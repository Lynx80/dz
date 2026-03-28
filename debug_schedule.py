import aiohttp
import asyncio
import json

async def test():
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NTQ1ODk5LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSw2MWI6Nzk6W10sNjY0Ojg2OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTM5NDIwOSwiaWF0IjoxNzc0NTQ1ODk5LCJqdGkiOiI2ZTljNmIwOC1mMjRiLTQzNmQtOWM2Yi0wOGYyNGI2MzZkYzMifQ.MmbPCkXrdAet4i-Q_dgA9TQ-wh0CURcgIuHBhvNaHBdA-VUz6LCbgbxgCcp5OtsZvB9hFmDZUulYt4BQlfhCYaMzALaWRenXmpTzT5gto4r9nhPdYAlEXZr7pkHub0mh690OrzFAN_23lMi0JMDEGX4W_gpwZcj81rQbJhZWhFhMvXItpil-GlYYfuJtRqD40CZ_qSGbJZepgQcQjDkDJO1E5Uc7A1i-pzIVWR5N7wf-A25qRMmnyegMLT4M_QbfzXoaNIio_GV_BT61Oi_5x0H45Wie_5uKvQhrnzILZTQOWQ5Ocj8kCUON3zmKMOdXF08IW1pw0NZbN75SMwK32w"
    student_id = "2584884"
    mesh_id = "7c0be908-fe90-4a99-83ed-aec4ece7948d"
    date = "2026-03-26"
    
    proxies = "http://89.110.73.28:1080"
    # Note: aiohttp doesn't support socks5 directly without aiohttp_socks
    # I'll use regular request if proxy is not absolute necessity for this debug
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    urls = [
        (f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?personId={student_id}&beginDate={date}&endDate={date}", "familyweb"),
        (f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?personIds={student_id}&beginDate={date}&endDate={date}", "familyweb"),
        (f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?personId={mesh_id}&beginDate={date}&endDate={date}", "familyweb"),
        (f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?personIds={mesh_id}&beginDate={date}&endDate={date}", "familyweb"),
        (f"https://api.myschool.mosreg.ru/family/mobile/v1/schedule?student_id={student_id}&date={date}", "familymp"),
        (f"https://api.myschool.mosreg.ru/family/mobile/v1/schedule/short?student_id={student_id}&from={date}&to={date}", "familymp"),
    ]
    
    async with aiohttp.ClientSession() as session:
        for url, sub in urls:
            h = headers.copy()
            h["X-Mes-Subsystem"] = sub
            h["X-Mes-Role"] = "student"
            # Try with apikey too
            h["apikey"] = "7ef6c62c-7b00-4796-96c6-2c7b00279619"
            
            # Handshake
            await session.get("https://myschool.mosreg.ru/acl/api/users/profile_info", headers=h)
            
            async with session.get(url, headers=h) as resp:
                print(f"URL: {url} | Sub: {sub} | Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  Count: {len(data.get('response', data.get('data', data)))}")
                    if data:
                        print(f"  Sample: {json.dumps(data, ensure_ascii=False)[:200]}")

if __name__ == "__main__":
    asyncio.run(test())
