import asyncio
from parser import ParserService
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test_library_fix():
    ps = ParserService()
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI4NzIwLCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI4NzIwLCJqdGkiOiIwNzVmMDk2My03OWNjLTRkNTEtOWYwOS02Mzc5Y2NlZDUxODEifQ.LCyd29UM9kPh31h0BrlMT3ZxlAfHW04jvDABh0F8stJLCxO-LtKv4e7ZMDu143lu1bq0VAvWjcT-ywhLImbUqQuCcpCj4hkoDe0ESvI6g0hwKe9ny3xq3UgmRtGRBkR6RqSvegMgvludGs1U30QkSYDjv4jLrxkabARhB1j_-EyfcW2dR__EIGl9hykhdN0KR1jdptxisPi7BwqiK3ZNKjDsHZsQMp2R_hzXghsdkQwqCps6chVFRZzDMj5QIBMtn4Lp5L1YEAArn-CSJc6IKzkx04WXSc-SPMYCZkeDcDhp-IKLNbu0BZLyu8Gsl6uAHXCFi2RkVXhxzn1O86Nhfg"
    student_id = "2584884"
    date = "2026-03-18" 
    mesh_id = "7c0be908-fe90-4a99-83ed-aec4ece7948d" # GUID
    
    print(f"\n--- TESTING ParserService.get_mosreg_schedule FOR {date} ---")
    lessons = await ps.get_mosreg_schedule(token, student_id, date, mesh_id=mesh_id)
    
    print(f"\nFINAL RESULT: Found {len(lessons)} lessons")
    for i, l in enumerate(lessons):
        print(f"{i+1}. [{l.get('time')}] {l.get('subject')}")
        if l.get('hw'):
            print(f"   HW: {l.get('hw')[:100]}...")
        if l.get('materials'):
            print(f"   Materials: {len(l.get('materials'))} links found")

if __name__ == "__main__":
    asyncio.run(test_library_fix())
