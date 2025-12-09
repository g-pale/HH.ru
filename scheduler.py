"""
Планировщик для автоматического запуска бота
Резюме можно поднимать раз в 4 часа, поэтому можно настроить запуск каждые 4 часа
"""
import schedule
import time
from loguru import logger
from hh_bot import HHResumeBot
from config import Config


def run_bot():
    """Запуск бота для поднятия резюме"""
    logger.info("=" * 50)
    logger.info("Запуск запланированного поднятия резюме")
    logger.info("=" * 50)
    
    try:
        with HHResumeBot() as bot:
            success = bot.update_resume()
            if success:
                logger.success("Резюме успешно поднято по расписанию!")
            else:
                logger.error("Не удалось поднять резюме по расписанию")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении задачи: {e}")


def main():
    """Основная функция планировщика"""
    # Настройка логирования
    logger.add("logs/scheduler_{time}.log", rotation="1 day", retention="30 days")
    
    # Проверка конфигурации
    errors = Config.validate()
    if errors:
        logger.error("Ошибки конфигурации:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.info("Пожалуйста, создайте файл .env на основе .env.example и заполните его")
        return
    
    # Настройка расписания
    # Планируем задачу на указанное время каждый день (закомментировано)
    # schedule_time = Config.SCHEDULE_TIME
    # schedule.every().day.at(schedule_time).do(run_bot)
    # logger.info(f"Планировщик настроен на запуск каждый день в {schedule_time}")
    
    # Запуск каждые 5 часов (с запасом, так как резюме можно поднимать раз в 4 часа)
    schedule.every(5).hours.do(run_bot)
    logger.info("Планировщик настроен на запуск каждые 5 часов")
    
    # Можно также запустить сразу при старте (для тестирования)
    # Раскомментируйте следующую строку, если хотите запустить сразу:
    # run_bot()
    
    logger.info("Планировщик запущен. Ожидание времени выполнения...")
    logger.info("Для остановки нажмите Ctrl+C")
    
    # Бесконечный цикл проверки расписания
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту
    except KeyboardInterrupt:
        logger.info("Планировщик остановлен пользователем")


if __name__ == "__main__":
    main()


