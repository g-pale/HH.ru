"""
Планировщик для автоматического запуска бота
Резюме можно поднимать раз в 4 часа, поэтому можно настроить запуск каждые 4 часа
Поддерживает поднятие всех резюме за один запуск (одна авторизация для всех резюме)
"""
import schedule
import time
from loguru import logger
from hh_bot import HHResumeBot
from config import Config


def run_bot():
    """
    Запуск бота для поднятия всех резюме за один раз
    Бот авторизуется один раз и поднимает все резюме подряд
    """
    logger.info("=" * 50)
    logger.info("Запуск запланированного поднятия резюме")
    logger.info("=" * 50)
    
    resume_ids = Config.get_resume_ids()
    if not resume_ids:
        logger.error("Не указаны ID резюме в конфигурации")
        return
    
    logger.info(f"Найдено резюме для поднятия: {len(resume_ids)}")
    logger.info("Бот авторизуется один раз и поднимет все резюме подряд")
    
    success_count = 0
    fail_count = 0
    
    try:
        # Создаем один экземпляр бота (одна авторизация)
        with HHResumeBot() as bot:
            # Проходим по всем резюме и поднимаем их подряд
            for index, resume_id in enumerate(resume_ids, 1):
                logger.info("-" * 50)
                logger.info(f"Поднимаем резюме #{index} из {len(resume_ids)}: {resume_id}")
                
                try:
                    success = bot.update_resume(resume_id)
                    if success:
                        logger.success(f"✓ Резюме #{index} ({resume_id}) успешно поднято!")
                        success_count += 1
                    else:
                        logger.warning(f"✗ Не удалось поднять резюме #{index} ({resume_id})")
                        fail_count += 1
                except Exception as e:
                    logger.error(f"✗ Ошибка при поднятии резюме #{index} ({resume_id}): {e}")
                    fail_count += 1
                
                # Небольшая задержка между поднятиями (2 секунды)
                # Чтобы не было слишком быстро и не вызвать подозрений
                if index < len(resume_ids):
                    logger.debug(f"Ожидание 2 секунды перед следующим резюме...")
                    time.sleep(2)
            
            logger.info("=" * 50)
            logger.info(f"Итоги поднятия резюме:")
            logger.info(f"  Успешно: {success_count} из {len(resume_ids)}")
            logger.info(f"  Ошибок: {fail_count} из {len(resume_ids)}")
            logger.info("=" * 50)
            
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении задачи: {e}")
        logger.exception("Детали ошибки:")


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


