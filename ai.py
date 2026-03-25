import logging
import json
import asyncio

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.api_key = "MOCK_MODE"
        self.api_url = "MOCK_URL"

    async def get_answer(self, question, options=None, image_b64=None):
        """Mock version of AIService that returns answers without calling Gemini API."""
        print(f"MOCK AI: Analyzing question: {question[:50]}...")
        
        # Simple logic: pick the first option OR just a text response
        if options:
            mock_response = {
                "type": "SINGLE",
                "answer": 1,
                "confidence": 1.0,
                "explanation": "Это тестовый ответ от Mock AI (лимиты Gemini превышены)."
            }
        else:
            mock_response = {
                "type": "TEXT",
                "answer": "Тестовый ответ",
                "confidence": 1.0,
                "explanation": "Это тестовый ответ от Mock AI."
            }
            
        return mock_response
