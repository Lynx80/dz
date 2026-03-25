import os
import httpx
import json
import logging

logger = logging.getLogger(__name__)

class AIHelper:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}"

    async def get_answer(self, question_text: str, options: list) -> str:
        """Получение ответа от ИИ (Gemini)"""
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found in .env. Returning mockup answer.")
            return "1" # Дефолтный ответ если нет ключа

        prompt = f"""
        Ты - эксперт в школьных предметах. Твоя задача - решить задание из теста.
        ВОПРОС: {question_text}
        ВАРИАНТЫ: {", ".join(options)}
        
        Верни ТОЛЬКО ОДНО число - индекс или текст правильного ответа. 
        Если это сопоставление, верни ответ в формате JSON: {{"item1": "answer1", "item2": "answer2"}}.
        НИКАКИХ пояснений. Только результат.
        """

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.api_url, json=payload, timeout=30)
                if resp.status_code == 200:
                    result = resp.json()
                    answer = result['candidates'][0]['content']['parts'][0]['text'].strip()
                    logger.info(f"AI Answer: {answer}")
                    return answer
                else:
                    logger.error(f"AI Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"AI Exception: {e}")
        
        return "1"
