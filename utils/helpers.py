import re

def classify_hw(desc: str, url: str) -> tuple[str, str]:
    """Возвращает (тип, иконка)"""
    desc_l = desc.lower().strip()
    url_l = url.lower() if url else ""
    
    # 0. ИГНОРИРУЕМ "БЕЗ ДЗ"
    if any(x in desc_l for x in ["без дз", "без д/з", "нет заданий", "не задано", "нет дз", "без домашнего задания"]) or not desc_l:
        return "нет", "🕊️"

    # 1. ТЕСТ (Приоритет ссылкам)
    if any(x in url_l for x in ["/test", "/exam", "/quiz", "/assessment", "/training", "videouroki.net/tests", "uchebnik.mos.ru/exam", "gosuslugi.ru/edu-content", "edu-content"]):
        return "тест", "⚡"
    
    # 2. ПИСЬМЕННОЕ (Приоритет действию)
    # Если есть номера, страницы или слова действия типа "выучить", "доделать"
    written_kws = ["номер", "стр.", "стр ", "с.", "упр", "упражнен", "задач", "параграф", "№", "выучить", "доделать", "сделать", "решить", "выполнить", "написать"]
    if any(x in desc_l for x in written_kws):
        return "письм.", "✍️"

    # 3. ТЕСТ (По ключевым словам в тексте)
    if any(x in desc_l for x in ["тест", "тренажер", "контрольн", "экзамен", "цдз", "📚"]):
        return "тест", "⚡"
    
    # 4. ВИДЕО
    if any(x in desc_l for x in ["видео", "посмотреть", "ролик", "видеоурок"]) or \
       any(x in url_l for x in ["youtube.com", "youtu.be", "rutube.ru", "vimeo.com", "/video/"]):
        return "видео", "📺"
        
    # 5. ТЕОРИЯ / МАТЕРИАЛ (Если не попало в письменное выше)
    if any(x in desc_l for x in ["прочитать", "повторить", "лекци", "материал", "правил", "изучить"]) or \
       any(x in url_l for x in ["/material", "/lesson", "/library", "resh.edu.ru"]):
        return "теория", "📖"
        
    # 6. ПО УМОЛЧАНИЮ
    return "письм.", "✍️"
