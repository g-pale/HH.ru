"""
Планировщик для автоматического запуска бота
Резюме можно поднимать раз в 4 часа, поэтому можно настроить запуск каждые 4 часа
Поддерживает поднятие всех резюме за один запуск (одна авторизация для всех резюме)
"""

import shutil
import signal
import subprocess
import sys
import time

import schedule
from loguru import logger
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

from browser_cleanup import (
    check_disk_space,
    cleanup_old_screenshots,
    cleanup_webdriver_manager_cache,
    kill_zombie_browsers,
)
from config import Config
from hh_bot import HHResumeBot

MAX_RETRIES = 2

# Текущий работающий бот — нужен, чтобы при остановке службы (systemctl stop,
# SIGTERM) корректно закрыть браузер через driver.quit(), а не бросить его
# зависшим процессом.
_active_bot = None
_shutdown_requested = False


def _handle_shutdown_signal(signum, _frame):
    """
    По умолчанию SIGTERM завершает процесс мгновенно, минуя весь Python-код
    (в т.ч. finally) — браузер остался бы висеть недоубитым. Перехватываем
    сигнал сами: закрываем текущий браузер штатно и только потом выходим.
    """
    global _shutdown_requested
    _shutdown_requested = True
    logger.warning(f"Получен сигнал {signum} — завершаем текущую работу и браузер...")
    if _active_bot is not None:
        try:
            _active_bot.close()
        except Exception:
            pass
    kill_zombie_browsers()
    logger.info("Ресурсы освобождены, выходим.")
    sys.exit(0)


def kill_zombie_browsers_before_start():
    """Убийство зависших процессов Chromium/Chrome перед запуском + уборка их мусора."""
    kill_zombie_browsers()
    time.sleep(1)


def log_memory():
    """Логирование текущего состояния памяти и диска"""
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

    try:
        usage = shutil.disk_usage("/")
        logger.debug(
            f"Диск /: занято {usage.used / (1024**3):.1f} ГБ, "
            f"свободно {usage.free / (1024**3):.1f} ГБ из {usage.total / (1024**3):.1f} ГБ"
        )
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
                    logger.info("Повторная попытка через 10 секунд...")
                    bot.restart_webdriver()
                    kill_zombie_browsers()
                    time.sleep(10)
        except (InvalidSessionIdException, WebDriverException) as e:
            logger.error(
                f"Браузер упал при поднятии резюме #{index} ({resume_id}): {e}"
            )
            bot.restart_webdriver()
            kill_zombie_browsers()
            if attempt < MAX_RETRIES:
                logger.info("Пересоздаём браузер, повторная попытка через 10 секунд...")
                time.sleep(10)
        except Exception as e:
            logger.error(f"Ошибка при поднятии резюме #{index} ({resume_id}): {e}")
            if attempt < MAX_RETRIES:
                logger.info("Повторная попытка через 10 секунд...")
                time.sleep(10)
    return False


def run_bot():
    """
    Запуск бота для поднятия всех резюме за один раз
    Бот авторизуется один раз и поднимает все резюме подряд
    """
    global _active_bot

    logger.info("=" * 50)
    logger.info("Запуск запланированного поднятия резюме")
    logger.info("=" * 50)

    # Проверка места на диске ДО запуска браузера: заполненный диск иначе
    # проявляется как InvalidSessionIdException и маскирует настоящую причину.
    check_disk_space()

    # Убиваем зависшие процессы браузера перед запуском
    logger.debug("Очистка зомби-процессов браузера...")
    kill_zombie_browsers_before_start()

    # Логирование состояния памяти и диска
    log_memory()

    resume_ids = Config.get_resume_ids()
    if not resume_ids:
        logger.error("Не указаны ID резюме в конфигурации")
        return

    logger.info(f"Найдено резюме для поднятия: {len(resume_ids)}")

    success_count = 0
    fail_count = 0

    bot = HHResumeBot()
    _active_bot = bot
    try:
        with bot:
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
        _active_bot = None
        # Гарантированная очистка процессов и осиротевших временных каталогов
        kill_zombie_browsers()
        # То, что растёт без ограничений само по себе и не чистится loguru
        cleanup_old_screenshots()
        cleanup_webdriver_manager_cache()
        log_memory()


def main():
    """Основная функция планировщика"""
    logger.add("logs/scheduler_{time}.log", rotation="1 day", retention="30 days")

    # SIGTERM (systemctl stop) по умолчанию завершает процесс мгновенно —
    # без обработчика браузер не успеет закрыться штатно.
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

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
        while not _shutdown_requested:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Планировщик остановлен пользователем")


if __name__ == "__main__":
    main()
