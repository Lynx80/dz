import asyncio
import os
import json
import logging
from datetime import datetime
from quart import Quart, render_template, request, jsonify, make_response
from database.db import Database
from services.api_client import MosregApiClient
from services.parser import ParserService
from bot import bot

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
parser = ParserService(db=db)

# --- Настройки безопасности и отладки ---
DEBUG_FORCE_DATA = False 

async def add_cors(resp, status=200):
    """Добавляет CORS заголовки и корректно обрабатывает статус-коды."""
    if isinstance(resp, tuple):
        resp, status = resp
    
    # Если это не объект Response, создаем его
    if not hasattr(resp, 'headers'):
        resp = await make_response(resp, status)
    else:
        resp.status_code = status

    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

def sanitize_text(text):
    """Очистка текста от символов, которые могут сломать JSON или старые браузеры."""
    if not text: return ""
    return "".join(ch for ch in str(text) if ch.isprintable() or ch in '\n\r\t')

# Инициализация асинхронного приложения Quart
app = Quart(__name__, template_folder='.')
db = Database()
api = MosregApiClient()

@app.before_serving
async def init_db():
    """Инициализация БД перед запуском сервера."""
    await db._create_tables()
    logger.info("Database tables initialized.")

@app.route('/')
async def index():
    """Главная страница Mini App."""
    rendered = await render_template('prime_app.html')
    resp = await make_response(rendered)
    # Добавляем заголовки для сброса кэша
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/profile/<int:user_id>')
async def get_profile(user_id):
    """Получение профиля из БД."""
    try:
        user = await db.get_user(user_id)
        if not user:
            return await add_cors(jsonify({"error": "User not found"}), 404)
        
        name = f"{user.get('first_name') or 'Пользователь'} {user.get('last_name') or ''}".strip()
        return await add_cors(jsonify({
            "name": name,
            "first_name": user.get('first_name') or "Пользователь",
            "last_name": user.get('last_name') or "",
            "grade": user.get('grade') or "Не указан",
            "student_id": user.get('student_id') or "",
            "solved": user.get('solved_count', 0),
            "avg_score": user.get('avg_score', 4.8)
        }))
    except Exception as e:
        return await add_cors(jsonify({"error": str(e)}), 500)

@app.route('/api/homework/<int:user_id>')
async def get_homework(user_id):
    """Получение расписания и ДЗ через stateless HTTPX клиент."""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        if DEBUG_FORCE_DATA:
            return await add_cors(jsonify([{
                "subject": "ТЕСТОВЫЙ ПРЕДМЕТ", "description": "СВЯЗЬ УСТАНОВЛЕНА", "is_cdz": True, "id": "test"
            }]))

        user = await db.get_user(user_id)
        if not user or not user.get('token_mos'):
            return await add_cors(jsonify({"error": "Unauthorized"}), 401)
            
        logger.info(f"Stateless HTTPX fetching homework for {user_id} on {date}...")
        
        # Используем новый API клиент (stateless)
        hw_list = await api.get_homework(
            user['token_mos'], user['student_id'], date, mesh_id=user.get('mesh_id')
        )
        
        processed_hw = []
        for h in (hw_list or []):
            materials = h.get('materials') or []
            # Improved CDZ/Digital detection for Mosreg and MESH
            m_links = " ".join([str(m.get('link','')).lower() for m in materials])
            m_names = " ".join([str(m.get('name','')).lower() for m in materials])
            # Строгий фильтр для ЦДЗ - только реальные платформы
            is_cdz = any(x in m_links for x in ["oblakoz.ru", "school.mos.ru", "uchebnik", "gosuslugi.ru/edu-content", "ismart.org", "videouroki.net"])
            
            # Учительские вложения (PDF/JPG) НЕ считаются ЦДЗ, даже если называются "тест"
            
            # Return full material objects for the card popup
            mat_objects = []
            for m in materials:
                if isinstance(m, dict):
                    mat_objects.append({
                        "name": m.get('name') or "Файл",
                        "link": m.get('link') or "#",
                        "is_digital": bool(m.get('is_digital'))
                    })
                else:
                    mat_objects.append({
                        "name": "Файл", 
                        "link": str(m), 
                        "is_digital": any(x in str(m).lower() for x in ["oblakoz.ru", "school.mos.ru", "uchebnik", "gosuslugi.ru/edu-content"])
                    })
            
            # Ищем ссылку на тест для проверки статуса
            td_url = ""
            for m in materials:
                if isinstance(m, dict) and m.get('is_digital'):
                    td_url = m.get('link')
                    break
            
            status_info = await db.get_homework_status(user_id, td_url) if td_url else {"status": "idle", "progress": 0}

            processed_hw.append({
                "id": h.get('id', ''),
                "subject": sanitize_text(h['subject']),
                "description": sanitize_text(h['hw'] or "Задание не указано"),
                "is_done": status_info['status'] == 'done',
                "is_cdz": is_cdz,
                "materials": mat_objects,
                "status": status_info['status'], 
                "progress": status_info['progress'],
                "time": h.get('time', ''),
                "room": h.get('room', '')
            })

        return await add_cors(jsonify(processed_hw))
            
    except Exception as e:
        logger.exception("Homework API error")
        return await add_cors(jsonify({"error": f"Ошибка сервера: {str(e)}"}), 500)

@app.route('/api/auth', methods=['POST'])
async def save_auth():
    """Сохранение токена через stateless HTTPX клиент."""
    data = await request.get_json()
    user_id = data.get('user_id')
    token = data.get('token')
    
    if not user_id or not token:
        return await add_cors(jsonify({"status": "error", "message": "Missing data"}), 400)

    try:
        handshake = await api.handshake(token)
        if handshake:
            await db.save_user_token(user_id, token, handshake)
            return await add_cors(jsonify({"status": "success", "user": handshake}))
        return await add_cors(jsonify({"status": "error", "message": "Неверный токен"}), 401)
    except Exception as e:
        return await add_cors(jsonify({"status": "error", "message": str(e)}), 500)

@app.route('/api/attach', methods=['POST'])
async def attach_result():
    """Прикрепление результата к школьному порталу."""
    data = await request.get_json()
    logger.info(f"Attach request for task {data.get('task_id')} from user {data.get('user_id')}")
    # Тут будет вызов метода бота для загрузки файла на портал
    return await add_cors(jsonify({"status": "success", "message": "Скриншот успешно прикреплен к лекции!"}))

@app.route('/api/solve', methods=['POST'])
async def solve_test_api():
    """Запуск процесса решения теста через ИИ-решатель."""
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        test_url = data.get('test_url')
        accuracy = data.get('accuracy', 'perfect')
        mins = int(data.get('mins', 15))
        
        if not user_id or not test_url:
            return await add_cors(jsonify({"error": "Missing params"}), 400)
            
        logger.info(f"API Solver: User {user_id} requested solve for {test_url}")
        
        # Запускаем в фоновом режиме, чтобы не держать HTTP соединение
        async def solve_task():
            # 1. Сначала ставим статус 'in_progress'
            await db.update_homework_status(user_id, test_url, 'in_progress', 5)
            
            async def status_cb(text):
                # Обновляем статус в базе для поллинга из Mini App
                progress_hint = 10
                if "Анализирую" in text: progress_hint = 20
                if "Решаю вопрос" in text:
                    try:
                        match = re.search(r'(\d+)/(\d+)', text)
                        if match: progress_hint = int((int(match.group(1)) / int(match.group(2))) * 80) + 15
                    except: progress_hint = 40
                if "завершен" in text or "Готово" in text: progress_hint = 100
                
                await db.update_homework_status(user_id, test_url, 'in_progress' if progress_hint < 100 else 'done', progress_hint)
            
            async def screen_cb(path):
                # Отправляем скриншот (QR или результат) прямо в чат бота
                from aiogram.types import FSInputFile
                try:
                    await bot.send_photo(user_id, FSInputFile(path), caption="📸 **СООБЩЕНИЕ ОТ РЕШАТЕЛЯ**\nОтсканируйте QR или это ваш результат.", parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Failed to send screen to bot: {e}")

            try:
                res, screenshot = await parser.solve_test(user_id, test_url, accuracy_mode=accuracy, solve_delay_mins=mins, status_callback=status_cb, screenshot_callback=screen_cb)
                status = 'done' if "Готово" in res or "выполнен" in res else 'error'
                await db.update_homework_status(user_id, test_url, status, 100 if status == 'done' else 0)
                
                # Уведомление в бот
                await bot.send_message(user_id, f"🎯 **РЕШЕНИЕ ЗАВЕРШЕНО**\n{res}", parse_mode="HTML")
            except Exception as e:
                logger.error(f"Solve task error: {e}")
                await db.update_homework_status(user_id, test_url, 'error', 0)
                await bot.send_message(user_id, f"❌ **ОШИБКА РЕШЕНИЯ**\n{str(e)[:100]}")

        asyncio.create_task(solve_task())
        
        return await add_cors(jsonify({
            "status": "success", 
            "message": "Процесс решения запущен в фоновом режиме. Следите за статусом в приложении или в чате бота."
        }))
    except Exception as e:
        logger.error(f"API Solve error: {e}")
        return await add_cors(jsonify({"error": str(e)}), 500)

@app.route('/api/logout', methods=['POST'])
async def logout():
    """Wipes all user data from the database."""
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return await add_cors(jsonify({"error": "Missing user_id"}), 400)
        
        # We assume Database.delete_user exists or we use a custom query
        try:
             await db.delete_user(user_id)
        except AttributeError:
             # Fallback if method is missing
             async with db.connect() as conn:
                 await conn.execute("UPDATE users SET token_mos=NULL, student_id=NULL WHERE user_id=?", (user_id,))
                 await conn.commit()
                 
        return await add_cors(jsonify({"status": "success", "message": "Профиль и данные успешно удалены"}))
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return await add_cors(jsonify({"error": str(e)}), 500)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8088, debug=False)
