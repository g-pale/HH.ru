"""
Общие функции для управления процессами Chromium/Chrome и уборки их
временных файлов.

Почему это отдельный модуль и зачем он нужен:
резкий SIGKILL (как было раньше — `pkill -9`) не даёт Chromium корректно
завершиться и убрать временный каталог профиля. После SIGKILL такие каталоги
остаются на диске навсегда. На VDS с snap-версией Chromium они лежат не в
обычном /tmp, а в изолированном "приватном" tmp снапа:

    org.chromium.Chromium.scoped_dir.XXXXXX  (видно изнутри snap-песочницы как /tmp/...)
    -> на хосте реально лежит в /tmp/snap-private-tmp/snap.chromium/tmp/...

Здесь мы:
1) завершаем зависшие процессы мягко (SIGTERM -> пауза -> SIGKILL только для
   тех, кто не ответил на SIGTERM);
2) убираем осиротевшие каталоги профилей по хостовому пути;
3) проверяем свободное место на диске и делаем принудительную уборку, если
   места стало мало (заполненный диск иначе маскируется под
   InvalidSessionIdException при следующем запуске браузера);
4) чистим то, что растёт без ограничений сама по себе: старые скриншоты
   логов и старые версии ChromeDriver в кэше webdriver-manager.
"""

import glob
import os
import shutil
import signal
import subprocess
import time

from loguru import logger

MIN_FREE_DISK_GB_DEFAULT = 2

# Snap изолирует /tmp контейнера Chromium: путь "/tmp/..." виден таким ТОЛЬКО
# изнутри песочницы браузера. Снаружи (там, где работает этот Python-процесс)
# тот же каталог лежит по хостовому пути ниже. Чистить нужно именно его.
CHROMIUM_SNAP_TMP_CANDIDATES = [
    "/tmp/snap-private-tmp/snap.chromium/tmp",
    "/tmp/snap-private-tmp/snap.chromium-browser/tmp",
]

BROWSER_PROCESS_PATTERNS = ["chromium", "chrome", "chromedriver"]


def _pgrep_pids(pattern) -> set:
    """PID-ы процессов, чья командная строка содержит pattern."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5
        )
        return {int(p) for p in result.stdout.split() if p.strip().isdigit()}
    except Exception:
        return set()


def kill_processes_gracefully(patterns=None, term_wait_sec=3):
    """
    SIGTERM всем найденным процессам, пауза, SIGKILL — только тем, кто не
    завершился сам. Даёт Chromium шанс убрать свой временный профиль перед
    выходом (после SIGKILL это уже невозможно).
    """
    patterns = patterns or BROWSER_PROCESS_PATTERNS
    pids = set()
    for pattern in patterns:
        pids |= _pgrep_pids(pattern)
    if not pids:
        return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:
            pass

    time.sleep(term_wait_sec)

    still_alive = set()
    for pid in pids:
        try:
            os.kill(pid, 0)  # процесс жив, если не выброшено исключение
            still_alive.add(pid)
        except ProcessLookupError:
            pass
        except Exception:
            still_alive.add(pid)

    for pid in still_alive:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    if still_alive:
        logger.debug(
            f"SIGKILL применён к {len(still_alive)} процессам, "
            f"не завершившимся по SIGTERM за {term_wait_sec}с"
        )


def kill_zombie_browsers():
    """Убийство зависших процессов Chromium/Chrome/chromedriver (мягко) + уборка их мусора."""
    try:
        kill_processes_gracefully()
        time.sleep(1)
    except Exception:
        pass
    cleanup_chromium_temp_dirs()


def cleanup_chromium_temp_dirs(force: bool = False) -> int:
    """
    Удаляет осиротевшие каталоги org.chromium.Chromium.scoped_dir.* — то, что
    остаётся после SIGKILL или краша Chromium и никогда не убирается само.

    force=False (по умолчанию): уборка выполняется только если процессов
    chromium не осталось — чтобы не задеть каталог, которым пользуется живой
    браузер.
    force=True: убрать принудительно (используется при нехватке места на
    диске, когда важнее освободить место, чем дождаться штатного завершения).
    """
    if not force and _pgrep_pids("chromium"):
        logger.debug("Chromium ещё работает — уборку временных профилей пропускаем")
        return 0

    removed = 0
    for base in CHROMIUM_SNAP_TMP_CANDIDATES:
        if not os.path.isdir(base):
            continue
        pattern = os.path.join(base, "org.chromium.Chromium.scoped_dir*")
        for path in glob.glob(pattern):
            try:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            except Exception as e:
                logger.debug(f"Не удалось удалить {path}: {e}")

    if removed:
        logger.info(f"Уборка Chromium: удалено {removed} осиротевших каталогов профиля")
    return removed


def check_disk_space(min_free_gb: float = MIN_FREE_DISK_GB_DEFAULT, path: str = "/"):
    """
    Проверка свободного места ДО запуска браузера. При нехватке — явное
    предупреждение в лог и принудительная уборка временных файлов Chromium.

    Важно: заполненный диск на практике проявляется как
    InvalidSessionIdException при попытке создать сессию Selenium — то есть
    настоящая причина маскируется под ошибку драйвера. Эта проверка делает
    причину видимой в логах явно, а не только через побочный симптом.
    """
    try:
        free_gb = shutil.disk_usage(path).free / (1024**3)
    except Exception as e:
        logger.debug(f"Не удалось проверить свободное место на {path}: {e}")
        return None

    if free_gb < min_free_gb:
        logger.warning(
            f"Мало места на диске {path}: {free_gb:.1f} ГБ свободно "
            f"(порог {min_free_gb} ГБ). Выполняем принудительную уборку "
            f"временных файлов Chromium перед запуском браузера..."
        )
        cleanup_chromium_temp_dirs(force=True)
        try:
            free_gb = shutil.disk_usage(path).free / (1024**3)
            logger.info(f"После уборки свободно на {path}: {free_gb:.1f} ГБ")
        except Exception:
            pass

    return free_gb


def cleanup_old_screenshots(log_dir: str = "logs", max_age_days: int = 7) -> int:
    """
    loguru rotation/retention чистит только собственные *.log файлы — файлы
    скриншотов (logs/*.png), которые сохраняет бот при ошибках, ей не видны
    и без этой функции остаются навсегда.
    """
    if not os.path.isdir(log_dir):
        return 0

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in glob.glob(os.path.join(log_dir, "*.png")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except Exception as e:
            logger.debug(f"Не удалось удалить {path}: {e}")

    if removed:
        logger.info(f"Уборка логов: удалено {removed} старых скриншотов из {log_dir}")
    return removed


def cleanup_webdriver_manager_cache(base_dir: str = None, keep_latest: int = 2) -> int:
    """
    webdriver-manager кэширует каждую версию ChromeDriver отдельно и не
    удаляет старые сама. После обновлений Chromium они копятся в ~/.wdm.
    Оставляем keep_latest последних по времени изменения версий, остальное
    удаляем.
    """
    base_dir = base_dir or os.path.expanduser("~/.wdm/drivers/chromedriver")
    if not os.path.isdir(base_dir):
        return 0

    version_dirs = []
    for platform_dir in glob.glob(os.path.join(base_dir, "*")):
        if not os.path.isdir(platform_dir):
            continue
        for version_dir in glob.glob(os.path.join(platform_dir, "*")):
            if os.path.isdir(version_dir):
                try:
                    version_dirs.append((os.path.getmtime(version_dir), version_dir))
                except OSError:
                    pass

    version_dirs.sort(key=lambda item: item[0], reverse=True)

    removed = 0
    for _, path in version_dirs[keep_latest:]:
        try:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
        except Exception as e:
            logger.debug(f"Не удалось удалить {path}: {e}")

    if removed:
        logger.info(
            f"Уборка кэша webdriver-manager: удалено {removed} старых версий ChromeDriver"
        )
    return removed
