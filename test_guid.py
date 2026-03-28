import asyncio
from parser import ParserService
import json

async def test_guid():
    ps = ParserService()
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI4NzIwLCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI4NzIwLCJqdGkiOiIwNzVmMDk2My03OWNjLTRkNTEtOWYwOS02Mzc5Y2NlZDUxODEifQ.LCyd29UM9kPh31h0BrlMT3ZxlAfHW04jvDABh0F8stJLCxO-LtKv4e7ZMDu143lu1bq0VAvWjcT-ywhLImbUqQuCcpCj4hkoDe0ESvI6g0hwKe9ny3xq3UgmRtGRBkR6RqSvegMgvludGs1U30QkSYDjv4jLrxkabARhB1j_-EyfcW2dR__EIGl9hykhdN0KR1jdptxisPi7BwqiK3ZNKjDsHZsQMp2R_hzXghsdkQwqCps6chVFRZzDMj5QIBMtn4Lp5L1YEAArn-CSJc6IKzkx04WXSc-SPMYCZkeDcDhp-IKLNbu0BZLyu8Gsl6uAHXCFi2RkVXhxzn1O86Nhfg"
    # REAL GUID from DB
    guid = "7c0be908-fe90-4a99-83ed-aec4ece7948d"
    date = "2026-03-18"
    
    url = f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events?person_ids={guid}&begin_date={date}&end_date={date}&expand=homework,marks&source_types=PLAN,AE,EC,EVENTS"
    
    session = await ps._get_session()
    headers = ps.base_headers.copy()
    headers.update({
        'Authorization': f'Bearer {token}',
        'X-Mes-Subsystem': 'familyweb',
        'X-Mes-Role': 'student',
        'profile-id': '2833290'
    })
    
    await ps._activate_session(token, subsystem='familyweb')
    
    async with session.get(url, headers=headers) as resp:
        print(f"Status: {resp.status}")
        data = await resp.json()
        items = data.get('response') or []
        print(f"Items found with GUID ({guid}): {len(items)}")
        for it in items[:10]:
            print(f"  - {it.get('subject_name')} (Source: {it.get('source')})")

if __name__ == "__main__":
    asyncio.run(test_guid())
