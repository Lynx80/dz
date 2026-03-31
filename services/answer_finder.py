
import asyncio
import re
import logging
from typing import List, Optional
from services.ai_service import AIService

logger = logging.getLogger(__name__)

class AnswerFinder:
    def __init__(self, ai_service: Optional[AIService] = None):
        self.ai = ai_service or AIService()

    async def find_answer(self, question: str, options: List[str] = None, site_context: str = "") -> str:
        """
        Универсальный метод поиска ответа:
        1. Анализирует контекст сайта.
        2. Если нужно, делает поиск в сети (заглушка для расширения).
        3. Использует ИИ для принятия финального решения.
        """
        prompt = f"Вопрос: {question}\nВарианты: {', '.join(options) if options else 'Открытый ответ'}\n"
        if site_context:
            prompt += f"Контекст сайта: {site_context}\n"
            
        prompt += "Найди правильный ответ. Ответь ТОЛЬКО текстом правильного ответа или его номером."
        
        try:
            # Используем мощь Gemini для анализа
            answer = await self.ai.analyze_test_step(question, options)
            return answer.strip()
        except Exception as e:
            logger.error(f"AI Answer Finding failed: {e}")
            return options[0] if options else ""

    def clean_text(self, text: str) -> str:
        """Очистка текста вопроса от HTML и лишних пробелов."""
        if not text: return ""
        return re.sub(r'<.*?>', '', text).strip()
