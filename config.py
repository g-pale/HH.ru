"""
Конфигурация для бота поднятия резюме на hh.ru
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class Config:
    """Класс для хранения конфигурации"""
    
    # Учетные данные
    HH_LOGIN = os.getenv('HH_LOGIN', '')
    HH_PASSWORD = os.getenv('HH_PASSWORD', '')
    HH_ACCESS_TOKEN = os.getenv('HH_ACCESS_TOKEN', '')
    
    # ID резюме (поддержка одного или нескольких через запятую)
    RESUME_ID = os.getenv('RESUME_ID', '')  # Для обратной совместимости
    RESUME_IDS = [r.strip() for r in os.getenv('RESUME_IDS', '').split(',') if r.strip()] if os.getenv('RESUME_IDS') else []
    
    # Если указан RESUME_IDS, используем его, иначе используем RESUME_ID
    @classmethod
    def get_resume_ids(cls):
        """Получить список ID резюме"""
        if cls.RESUME_IDS:
            return cls.RESUME_IDS
        elif cls.RESUME_ID:
            return [cls.RESUME_ID]
        else:
            return []
    
    # Настройки расписания
    SCHEDULE_TIME = os.getenv('SCHEDULE_TIME', '09:00')
    
    # Настройки браузера (для веб-автоматизации)
    HEADLESS_BROWSER = os.getenv('HEADLESS_BROWSER', 'true').lower() == 'true'
    BROWSER_TYPE = os.getenv('BROWSER_TYPE', 'chrome')
    
    # URL для работы с hh.ru
    HH_BASE_URL = 'https://hh.ru'
    HH_LOGIN_URL = 'https://hh.ru/account/login'
    
    # API endpoints (если доступны)
    HH_API_BASE_URL = 'https://api.hh.ru'
    
    @classmethod
    def validate(cls):
        """Проверка наличия необходимых данных"""
        errors = []
        
        resume_ids = cls.get_resume_ids()
        if not resume_ids:
            errors.append("Не указаны ID резюме. Укажите RESUME_ID или RESUME_IDS в .env файле")
        
        if not cls.HH_ACCESS_TOKEN and (not cls.HH_LOGIN or not cls.HH_PASSWORD):
            errors.append("Необходимо указать либо HH_ACCESS_TOKEN, либо HH_LOGIN и HH_PASSWORD")
        
        return errors


