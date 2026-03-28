import os
import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Correct imports matching main.py
from database.db import Database
from services.parser import ParserService, MosregAuthError

# Load environment
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    # Use the one from bot.py as fallback if needed for local test, 
    # but normally it should be in .env
    BOT_TOKEN = "8684063011:AAHpBjpulnliaz2-Qnnvh_DPUwQaNygj8lg"

app = FastAPI(title="DZ Helper API")
db = Database()
parser = ParserService()

@app.on_event("startup")
async def startup_event():
    import aiohttp
    app.state.session = aiohttp.ClientSession()
    parser.session = app.state.session

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.session.close()

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class UserData(BaseModel):
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    grade: Optional[str] = None

class ActionRequest(BaseModel):
    user_id: int
    action: str
    params: dict

# --- UTILS ---
def verify_telegram_init_data(init_data: str) -> bool:
    if not init_data:
        return False
        
    try:
        # В режиме разработки можно пропустить проверку
        if os.getenv("DEBUG") == "True":
            return True
            
        parsed_data = dict(x.split('=') for x in init_data.split('&'))
        hash_str = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return calculated_hash == hash_str
    except:
        return False

# --- API ENDPOINTS ---

@app.get("/api/user_data")
async def get_user_data(user_id: int, init_data: str = Header(None)):
    # verify logic...
    
    user = await db.get_user(user_id)
    if not user:
        # Create user if it doesn't exist
        await db.create_user(user_id, first_name="Студент")
        user = await db.get_user(user_id)
        
    stats = await db.get_stats(user_id)
    
    return {
        "user": {
            "id": user['user_id'],
            "first_name": user['first_name'],
            "last_name": user.get('last_name', ''),
            "grade": user.get('grade', 'Не указан'),
            "status": "✅ Подключен" if user.get('token_mos') else "❌ Не привязан"
        },
        "stats": {
            "solved": stats['solved'],
            "avg": stats['avg'],
            "saved": stats['saved']
        },
        "settings": {
            "solve_delay": user.get('solve_delay', 15),
            "accuracy_mode": user.get('accuracy_mode', 'advanced')
        }
    }

@app.get("/api/homework")
async def get_day_homework(user_id: int, date: str, init_data: str = Header(None)):
    user = await db.get_user(user_id)
    if not user or not user.get('token_mos'):
        raise HTTPException(status_code=401, detail="Token missing")
        
    try:
        schedule = await parser.get_mosreg_schedule(user['token_mos'], user['student_id'], date, mesh_id=user.get('mesh_id'))
        homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date, mesh_id=user.get('mesh_id'))
        
        formatted_hw = []
        for item in (schedule or []):
            hw_item = next((h for h in homeworks if h['subject'].lower() in item['subject'].lower() or item['subject'].lower() in h['subject'].lower()), None)
            
            hw_data = {
                "lesson_id": item.get('id', 0),
                "subject": item['subject'],
                "time": item['time'],
                "room": item['room'],
                "text": "Без домашнего задания",
                "status": "none",
                "type": "none",
                "links": []
            }
            
            if hw_item:
                desc = hw_item['description'].strip()
                hw_hash = hashlib.md5(f"{item['subject'].strip()}:{desc}".encode()).hexdigest()
                is_done = await db.is_hw_completed(user_id, date, hw_hash)
                
                hw_data["text"] = desc
                hw_data["status"] = "done" if is_done else "pending"
                
                # Simple type detection
                if any(x in desc.lower() for x in ["тест", "цдз", "мэш"]): hw_data["type"] = "test"
                elif any(x in desc.lower() for x in ["стр", "номер", "упр"]): hw_data["type"] = "written"
                
                # Materials
                for m in hw_item.get('materials', []):
                    hw_data["links"].append({"title": m.get('title', 'Материал'), "link": m.get('link', '')})
                    
            formatted_hw.append(hw_data)
            
        return {"schedule": schedule, "homework": formatted_hw}
    except Exception as e:
        logging.error(f"Error fetching homework: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/action")
async def perform_action(req: ActionRequest):
    if req.action == "solve":
        # Placeholder for solving logic
        return {"status": "success", "message": "Задание отправлено в решение"}
    return {"status": "error", "message": "Unknown action"}

# --- STATIC FILES ---
# Ensure the path is absolute
webapp_path = os.path.join(os.path.dirname(__file__), "webapp")
app.mount("/", StaticFiles(directory=webapp_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 for accessibility
    uvicorn.run(app, host="0.0.0.0", port=8000)
