"""
Планировщик для автоматического запуска бота
Резюме можно поднимать раз в 4 часа, поэтому можно настроить запуск каждые 4 часа
Поддерживает поднятие всех резюме за один запуск (одна авторизация для всех резюме)
"""

import subprocess
import schedule
import time
from loguru import logger
from hh_bot import HHResumeBot
from config import Config

MAX_RETRIES = 2


def kill_zombie_browsers():
    """Убийство всех зависших процессов Chromium/Chrome перед запуском"""
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "chromium"], capture_output=True, timeout=5
        )
        subprocess.run(["pkill", "-9", "-f", "chrome"], capture_output=True, timeout=5)
        subprocess.run(
            ["pkill", "-9", "-f", "chromedriver"], capture_output=True, timeout=5
        )
        time.sleep(2)
    except Exception:
        pass


def log_memory():
    """Логирование текущего состояния памяти"""
    try:
        result = subprocess.run(
            ["free", "-h"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines:
                logger.debug(f"Память: {line}")
    except Exception:
        pass


def run_bot_for_resume(bot, index, resume_id, total):
    """Поднятие одного резюме с повторными попытками"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                f"Поднимаем резюме #{index} из {total}: {resume_id}"
                + (f" (попытка {attempt})" if attempt > 1 else "")
            )
            success = bot.update_resume(resume_id)
            if success:
                logger.success(f"Резюме #{index} ({resume_id}) успешно поднято!")
                return True
            else:
                logger.warning(f"Не удалось поднять резюме #{index} ({resume_id})")
                if attempt < MAX_RETRIES:
                    logger.info("Повторная попытка через 5 секунд...")
                    time.sleep(5)
        except Exception as e:
            logger.error(f"Ошибка при поднятии резюме #{index} ({resume_id}): {e}")
            if attempt < MAX_RETRIES:
                logger.info("Повторная попытка через 5 секунд...")
                time.sleep(5)
    return False


def run_bot():
    """
    Запуск бота для поднятия всех резюме за один раз
    Бот авторизуется один раз и поднимает все резюме подряд
    """
    logger.info("=" * 50)
    logger.info("Запуск запланированного поднятия резюме")
    logger.info("=" * 50)

    # Убиваем зависшие процессы браузера перед запуском
    logger.debug("Очистка зомби-процессов браузера...")
    kill_zombie_browsers()

    # Логирование состояния памяти
    log_memory()

    resume_ids = Config.get_resume_ids()
    if not resume_ids:
        logger.error("Не указаны ID резюме в конфигурации")
        return

    logger.info(f"Найдено резюме для поднятия: {len(resume_ids)}")

    success_count = 0
    fail_count = 0

    try:
        with HHResumeBot() as bot:
            for index, resume_id in enumerate(resume_ids, 1):
                logger.info("-" * 50)

                result = run_bot_for_resume(bot, index, resume_id, len(resume_ids))
                if result:
                    success_count += 1
                else:
                    fail_count += 1

                if index < len(resume_ids):
                    if Config.BROWSER_RESTART_EACH_RESUME:
                        logger.debug(
                            "Перезапуск браузера перед следующим резюме (BROWSER_RESTART_EACH_RESUME)"
                        )
                        bot.restart_webdriver()
                    logger.debug("Ожидание 3 секунды перед следующим резюме...")
                    time.sleep(3)

            logger.info("=" * 50)
            logger.info("Итоги поднятия резюме:")
            logger.info(f"  Успешно: {success_count} из {len(resume_ids)}")
            logger.info(f"  Ошибок: {fail_count} из {len(resume_ids)}")
            logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении задачи: {e}")
        logger.exception("Детали ошибки:")
    finally:
        # Гарантированная очистка процессов после завершения
        kill_zombie_browsers()
        log_memory()


def main():
    """Основная функция планировщика"""
    logger.add("logs/scheduler_{time}.log", rotation="1 day", retention="30 days")

    errors = Config.validate()
    if errors:
        logger.error("Ошибки конфигурации:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.info(
            "Пожалуйста, создайте файл .env на основе .env.example и заполните его"
        )
        return

    resume_ids = Config.get_resume_ids()
    logger.info(f"Найдено {len(resume_ids)} резюме для поднятия")

    schedule.every(5).hours.do(run_bot)
    logger.info("Планировщик настроен на запуск каждые 5 часов")
    logger.info("Планировщик запущен. Ожидание времени выполнения...")
    logger.info("Для остановки нажмите Ctrl+C")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Планировщик остановлен пользователем")


if __name__ == "__main__":
    main()
