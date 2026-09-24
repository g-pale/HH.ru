"""
Бот для автоматического поднятия резюме на hh.ru
Поддерживает два метода: через API и через веб-автоматизацию
"""

import random
import re
import time
import requests
from loguru import logger
from selenium.webdriver.chromium.webdriver import ChromiumDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.driver_finder import DriverFinder
from selenium.webdriver.chromium.remote_connection import ChromiumRemoteConnection
from selenium.webdriver.remote.client_config import ClientConfig
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    InvalidSessionIdException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

from browser_cleanup import kill_zombie_browsers
from config import Config


class ChromeDriverWithHttpTimeout(ChromiumDriver):
    """
    Локальный Chrome/Chromium с увеличенным HTTP timeout до ChromeDriver.
    RemoteConnection.set_timeout() в Selenium 4.36+ падает (_client_config is None);
    таймаут задаётся через ClientConfig.
    """

    def __init__(self, service, options, http_timeout_sec: int) -> None:
        self.service = service
        finder = DriverFinder(self.service, options)
        if finder.get_browser_path():
            options.binary_location = finder.get_browser_path()
            options.browser_version = None
        self.service.path = self.service.env_path() or finder.get_driver_path()
        self.service.start()
        client_config = ClientConfig(
            remote_server_addr=self.service.service_url,
            keep_alive=True,
            timeout=http_timeout_sec,
        )
        executor = ChromiumRemoteConnection(
            remote_server_addr=self.service.service_url,
            browser_name=DesiredCapabilities.CHROME["browserName"],
            vendor_prefix="goog",
            keep_alive=True,
            ignore_proxy=options._ignore_local_proxy,
            client_config=client_config,
        )
        RemoteWebDriver.__init__(self, command_executor=executor, options=options)
        self._is_remote = False


class HHResumeBot:
    """Класс для автоматического поднятия резюме на hh.ru"""

    def __init__(self):
        self.config = Config
        self.session = requests.Session()
        self.driver = None
        self._is_logged_in = False  # Флаг авторизации для избежания повторных входов

    def restart_webdriver(self):
        """Закрыть только браузер (следующий вызов откроет новый и потребует вход)."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._is_logged_in = False

    def _apply_navigation_timeouts(self):
        """Таймауты навигации = SELENIUM_HTTP_READ_TIMEOUT (раньше был потолок 180 с — Chrome ронял рендерер ~155 с)."""
        if not self.driver:
            return
        try:
            t = max(120, int(self.config.SELENIUM_HTTP_READ_TIMEOUT))
            t = min(t, 600)
            self.driver.set_page_load_timeout(t)
            self.driver.set_script_timeout(t)
        except Exception:
            pass

    def _get_url_with_retry(
        self, url: str, *, attempts: int = 2, desc: str = "страница"
    ) -> None:
        """driver.get с повтором при TimeoutException (частично загруженная страница)."""
        self._apply_navigation_timeouts()
        last_exc = None
        for i in range(attempts):
            try:
                self.driver.get(url)
                return
            except TimeoutException as e:
                last_exc = e
                logger.warning(
                    f"Таймаут загрузки {desc} (попытка {i + 1}/{attempts}): {e}"
                )
                try:
                    self.driver.execute_script("window.stop();")
                except Exception:
                    pass
                if i < attempts - 1:
                    time.sleep(5)
        if last_exc:
            raise last_exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Закрытие браузера и сессии, убийство зомби-процессов"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.session.close()
        self._is_logged_in = False
        self._kill_zombie_browsers()

    @staticmethod
    def _kill_zombie_browsers():
        """
        Убийство зависших процессов Chromium/Chrome (мягко: сначала SIGTERM,
        SIGKILL — крайняя мера) и уборка их временных профилей в /tmp.
        Без этого резкий SIGKILL оставляет каталоги профилей навсегда —
        подробности в browser_cleanup.py.
        """
        kill_zombie_browsers()

    def update_resume_via_api(self, resume_id: str = None) -> bool:
        """
        Попытка поднять резюме через официальный API hh.ru
        ВАЖНО: Нужно проверить документацию API на наличие этого метода

        Args:
            resume_id: ID резюме для поднятия. Если не указан, используется первый из списка.
        """
        if not self.config.HH_ACCESS_TOKEN:
            logger.warning("OAuth токен не указан, пропускаем метод API")
            return False

        if not resume_id:
            resume_ids = self.config.get_resume_ids()
            if not resume_ids:
                logger.error("Не указан ID резюме")
                return False
            resume_id = resume_ids[0]

        headers = {
            "Authorization": f"Bearer {self.config.HH_ACCESS_TOKEN}",
            "User-Agent": "HH-Resume-Bot/1.0",
        }

        # ВАЖНО: Этот endpoint нужно проверить в документации API hh.ru
        # Возможные варианты:
        # - PUT /resumes/{resume_id}/publish
        # - POST /resumes/{resume_id}/update
        # - PUT /resumes/{resume_id}/publish_to_search

        api_url = f"{self.config.HH_API_BASE_URL}/resumes/{resume_id}/publish"

        try:
            response = self.session.put(api_url, headers=headers)

            if response.status_code == 200 or response.status_code == 204:
                logger.success(f"Резюме {resume_id} успешно поднято через API")
                return True
            else:
                logger.warning(
                    f"API вернул код {response.status_code}: {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Ошибка при работе с API: {e}")
            return False

    def _is_session_alive(self) -> bool:
        """Проверка, жива ли текущая сессия браузера."""
        if not self.driver:
            return False
        try:
            _ = self.driver.title
            return True
        except (InvalidSessionIdException, WebDriverException):
            return False

    def _init_browser(self):
        """Инициализация браузера для веб-автоматизации"""
        if self.driver:
            if self._is_session_alive():
                return
            logger.warning("Обнаружена мёртвая сессия браузера, пересоздаём...")
            self.restart_webdriver()

        try:
            http_timeout_sec = max(60, int(self.config.SELENIUM_HTTP_READ_TIMEOUT))
        except (TypeError, ValueError):
            http_timeout_sec = 240

        chrome_options = Options()
        pls = getattr(self.config, "CHROME_PAGE_LOAD_STRATEGY", "normal") or "normal"
        if pls not in ("normal", "eager", "none"):
            pls = "normal"
        chrome_options.page_load_strategy = pls

        if self.config.HEADLESS_BROWSER:
            chrome_options.add_argument("--headless")

        # Флаги для работы на сервере без GUI
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")  # Важно для серверов без GPU
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Устанавливаем User-Agent для имитации обычного браузера
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Увеличиваем размер окна для лучшей видимости элементов
        chrome_options.add_argument("--window-size=1920,1080")

        # Дополнительные флаги для стабильной работы на сервере
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-breakpad")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-hang-monitor")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-prompt-on-repost")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--metrics-recording-only")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--safebrowsing-disable-auto-update")
        chrome_options.add_argument("--password-store=basic")
        chrome_options.add_argument("--use-mock-keychain")

        # Отключаем уведомления
        prefs = {"profile.default_content_setting_values.notifications": 2}
        chrome_options.add_experimental_option("prefs", prefs)

        # Определяем, какой браузер использовать
        browser_type = self.config.BROWSER_TYPE.lower()
        use_chromium = browser_type == "chromium"

        # Проверка наличия браузера
        driver_version = None
        try:
            import subprocess

            if use_chromium:
                # Пробуем разные варианты команд Chromium
                browser_cmd = None
                browser_path = None
                for cmd in ["chromium-browser", "chromium"]:
                    try:
                        subprocess.check_output(
                            [cmd, "--version"], stderr=subprocess.STDOUT
                        )
                        browser_cmd = cmd
                        # Определяем путь к исполняемому файлу
                        browser_path = (
                            subprocess.check_output(["which", cmd]).decode().strip()
                        )
                        break
                    except Exception:
                        continue
                if not browser_cmd:
                    raise FileNotFoundError("Chromium не найден")
                browser_name = "Chromium"
            else:
                browser_cmd = "google-chrome"
                browser_name = "Chrome"
                browser_path = None

            browser_version = (
                subprocess.check_output(
                    [browser_cmd, "--version"], stderr=subprocess.STDOUT
                )
                .decode()
                .strip()
            )
            logger.debug(f"{browser_name} найден: {browser_version}")
            # Извлекаем мажорную версию (например 145 из "Chromium 145.0.7632.109")
            driver_version_match = re.search(r"(\d+)\.\d+\.\d+", browser_version)
            driver_version = (
                driver_version_match.group(1) if driver_version_match else None
            )
        except FileNotFoundError:
            logger.error(f"{browser_name} не найден!")
            logger.error("Установите браузер командой:")
            if use_chromium:
                logger.error("  apt install -y chromium-browser chromium-chromedriver")
            else:
                logger.error("  apt install -y google-chrome-stable")
            raise
        except Exception as e:
            logger.warning(f"Не удалось проверить версию {browser_name}: {e}")
            logger.info("Продолжаем попытку запуска...")

        # Установка ChromeDriver (версия под текущий браузер — избегает рассогласования после обновления Chromium)
        try:
            if driver_version:
                logger.debug(
                    f"Запрашиваем ChromeDriver для версии браузера {driver_version}"
                )
            manager = (
                ChromeDriverManager(driver_version=driver_version)
                if driver_version
                else ChromeDriverManager()
            )
            service = Service(manager.install())
        except Exception as e:
            logger.error(f"Ошибка при установке ChromeDriver: {e}")
            raise

        # Дополнительные флаги для серверов с ограниченной памятью
        if self.config.CHROMIUM_SINGLE_PROCESS:
            chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument(
            f"--remote-debugging-port={random.randint(20000, 59999)}"
        )
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-features=BlinkGenPropertyTrees")
        chrome_options.add_argument("--disable-features=CalculateNativeWinOcclusion")
        chrome_options.add_argument("--memory-pressure-off")

        # Меньше процессов рендерера — на VDS с 512 МБ снижает "Timed out receiving message from renderer"
        if self.config.HEADLESS_BROWSER:
            chrome_options.add_argument(
                "--disable-features=IsolateOrigins,site-per-process"
            )
            chrome_options.add_argument("--renderer-process-limit=2")

        # Создание драйвера с дополнительной обработкой ошибок
        try:
            if use_chromium and browser_path:
                # Для Chromium нужно указать путь к исполняемому файлу
                chrome_options.binary_location = browser_path
                logger.debug(f"Используется Chromium по пути: {browser_path}")

            self.driver = ChromeDriverWithHttpTimeout(
                service, chrome_options, http_timeout_sec
            )
            logger.debug(
                f"HTTP timeout Selenium↔ChromeDriver: {http_timeout_sec} с (ClientConfig)"
            )
            self.driver.implicitly_wait(10)
            self._apply_navigation_timeouts()
            logger.debug(f"{browser_name} успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при создании драйвера {browser_name}: {e}")
            logger.error("Возможные причины:")
            logger.error("1. Браузер не установлен или установлен неправильно")
            logger.error(
                "2. Недостаточно памяти (попробуйте увеличить swap: fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile)"
            )
            logger.error("3. Отсутствуют необходимые библиотеки")
            logger.error("4. ChromeDriver несовместим с версией браузера")
            logger.error("5. Попробуйте использовать Chromium вместо Chrome (легче)")
            raise

    def _find_element_by_multiple_selectors(
        self, selectors, by_type=By.CSS_SELECTOR, timeout=10
    ):
        """Поиск элемента по нескольким селекторам"""
        for selector in selectors:
            try:
                if by_type == By.XPATH:
                    element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                else:
                    element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                logger.debug(f"Элемент найден по селектору: {selector}")
                return element
            except Exception:
                continue
        return None

    def _check_logged_in(self) -> bool:
        """Проверка, авторизован ли пользователь"""
        if not self.driver:
            return False

        try:
            current_url = self.driver.current_url
            # Если не на странице входа, возможно уже авторизован
            if "account/login" not in current_url:
                # Проверяем наличие элементов личного кабинета
                try:
                    personal_elements = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        '[data-qa="mainmenu_applicantResumes"], [data-qa="mainmenu_myResumes"], [href*="/applicant/resumes"]',
                    )
                    if personal_elements:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _login(self) -> bool:
        """Авторизация на hh.ru (многошаговый процесс)"""
        # Если уже авторизован, пропускаем
        if self._is_logged_in and self._check_logged_in():
            logger.debug("Пользователь уже авторизован, пропускаем вход")
            return True

        try:
            logger.info("Начинаем авторизацию на hh.ru...")
            self._get_url_with_retry(
                self.config.HH_LOGIN_URL, attempts=2, desc="страницы входа"
            )
            time.sleep(3)

            # ШАГ 1: Выбор роли "Я ищу работу" и нажатие "Войти" (если нужно)
            logger.debug("Шаг 1: Проверяем выбор роли...")
            try:
                # Ищем карточку "Я ищу работу" через JavaScript
                role_element = self.driver.execute_script("""
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var text = elements[i].textContent.trim();
                        if (text.includes('Я ищу работу') || text.includes('Профиль соискателя')) {
                            // Ищем родительский кликабельный элемент
                            var parent = elements[i];
                            while (parent && parent !== document.body) {
                                if (parent.onclick || parent.getAttribute('role') === 'button' || 
                                    parent.tagName === 'BUTTON' || parent.tagName === 'A' ||
                                    parent.style.cursor === 'pointer') {
                                    return parent;
                                }
                                parent = parent.parentElement;
                            }
                            return elements[i];
                        }
                    }
                    return null;
                """)

                if role_element:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView(true);", role_element
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", role_element)
                    logger.debug("Роль 'Я ищу работу' выбрана")
                    time.sleep(1)

                    # После выбора роли нужно нажать кнопку "Войти"
                    login_button_step1 = self.driver.execute_script("""
                        var buttons = document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {
                            var text = buttons[i].textContent.trim();
                            if (text === 'Войти' || text.includes('Войти')) {
                                return buttons[i];
                            }
                        }
                        return null;
                    """)

                    if login_button_step1:
                        self.driver.execute_script(
                            "arguments[0].click();", login_button_step1
                        )
                        logger.debug("Кнопка 'Войти' нажата на первом шаге")
                        time.sleep(3)
            except Exception as e:
                logger.debug(f"Роль уже выбрана или не требуется: {e}")

            # ШАГ 2: Ввод email и нажатие "Дальше"
            logger.debug("Шаг 2: Вводим email...")

            # Сначала проверяем, есть ли вкладка "Почта" и выбираем её
            try:
                email_tab_selectors = [
                    '//*[contains(text(), "Почта")]',
                    '[data-qa="login-tab-email"]',
                    ".login-tab-email",
                ]

                for selector in email_tab_selectors:
                    try:
                        if selector.startswith("//"):
                            email_tab = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                        else:
                            email_tab = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                        email_tab.click()
                        logger.debug("Вкладка 'Почта' выбрана")
                        time.sleep(1)
                        break
                    except Exception:
                        continue
            except Exception:
                logger.debug("Вкладка 'Почта' не найдена или уже выбрана")

            # Поиск поля ввода email
            email_selectors = [
                'input[type="text"]',
                'input[type="email"]',
                'input[placeholder*="почт"]',
                'input[placeholder*="email"]',
                "input.bloko-input",
                'input[data-qa="login-input-username"]',
            ]

            email_input = self._find_element_by_multiple_selectors(
                email_selectors, timeout=10
            )
            if not email_input:
                logger.error("Не удалось найти поле ввода email")
                logger.info("Текущий URL: " + self.driver.current_url)
                self.driver.save_screenshot("logs/login_step1_error.png")
                return False

            # Вводим email
            email_input.clear()
            email_input.send_keys(self.config.HH_LOGIN)
            logger.debug(f"Email введен: {self.config.HH_LOGIN}")
            time.sleep(1)

            # ВАЖНО: Нажимаем кнопку "Войти с паролем" вместо "Дальше"
            # Это позволяет сразу перейти к вводу пароля, минуя запрос кода из письма
            logger.debug("Ищем кнопку 'Войти с паролем'...")

            # Прокручиваем страницу вниз, чтобы увидеть кнопку "Войти с паролем"
            try:
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight / 2);"
                )
                time.sleep(0.5)
            except Exception:
                pass

            # Находим кнопку через Selenium - ищем все кнопки и ссылки
            button_element = None

            try:
                # Ищем все кнопки
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                all_elements = all_buttons + all_links

                logger.debug(f"Найдено элементов для проверки: {len(all_elements)}")

                for elem in all_elements:
                    try:
                        text = elem.text.strip()
                        # Проверяем текст кнопки
                        if (
                            "Войти с паролем" in text
                            or "войти с паролем" in text.lower()
                        ):
                            # Проверяем видимость
                            if elem.is_displayed():
                                button_element = elem
                                logger.debug(
                                    f"Кнопка 'Войти с паролем' найдена через Selenium, текст: '{text}'"
                                )
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Ошибка при поиске через Selenium: {e}")

            # Если не нашли через Selenium, пробуем через XPath
            if not button_element:
                try:
                    button_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, '//*[contains(text(), "Войти с паролем")]')
                        )
                    )
                    logger.debug("Кнопка найдена через XPath")
                except Exception:
                    logger.debug("Кнопка не найдена через XPath")

            # Если все еще не нашли, пробуем через JavaScript
            if not button_element:
                try:
                    button_element = self.driver.execute_script("""
                        var elements = document.querySelectorAll('button, a');
                        for (var i = 0; i < elements.length; i++) {
                            var text = elements[i].textContent.trim();
                            if (text.includes('Войти с паролем') || text.includes('войти с паролем')) {
                                var style = window.getComputedStyle(elements[i]);
                                if (style.display !== 'none' && style.visibility !== 'hidden') {
                                    return elements[i];
                                }
                            }
                        }
                        return null;
                    """)
                    if button_element:
                        logger.debug("Кнопка найдена через JavaScript")
                except Exception as e:
                    logger.debug(f"Ошибка при поиске через JavaScript: {e}")

            if not button_element:
                logger.error("Не удалось найти кнопку 'Войти с паролем'")
                self.driver.save_screenshot("logs/login_password_button_not_found.png")
                return False

            # Кликаем по кнопке
            try:
                # Прокручиваем к кнопке
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                    button_element,
                )
                time.sleep(0.5)

                # Пробуем кликнуть разными способами
                clicked = False

                # Способ 1: Обычный клик через Selenium
                try:
                    button_element.click()
                    logger.debug(
                        "Кнопка 'Войти с паролем' нажата через Selenium click()"
                    )
                    clicked = True
                except Exception as e:
                    logger.debug(f"Ошибка при клике через Selenium: {e}")

                # Способ 2: Клик через ActionChains
                if not clicked:
                    try:
                        ActionChains(self.driver).move_to_element(
                            button_element
                        ).click().perform()
                        logger.debug(
                            "Кнопка 'Войти с паролем' нажата через ActionChains"
                        )
                        clicked = True
                    except Exception as e:
                        logger.debug(f"Ошибка при клике через ActionChains: {e}")

                # Способ 3: Клик через JavaScript
                if not clicked:
                    try:
                        self.driver.execute_script(
                            "arguments[0].click();", button_element
                        )
                        logger.debug("Кнопка 'Войти с паролем' нажата через JavaScript")
                        clicked = True
                    except Exception as e:
                        logger.debug(f"Ошибка при клике через JavaScript: {e}")

                if not clicked:
                    logger.error("Не удалось кликнуть по кнопке 'Войти с паролем'")
                    self.driver.save_screenshot(
                        "logs/login_password_button_click_error.png"
                    )
                    return False

                # Ждем изменения формы
                logger.debug("Ожидаем изменения формы после клика...")
                time.sleep(2)  # Даем время на загрузку формы

                # Проверяем появление поля пароля
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'input[type="password"]')
                        )
                    )
                    logger.debug("Форма изменилась - поле пароля появилось")
                except Exception:
                    logger.warning(
                        "Поле пароля не появилось сразу, продолжаем поиск..."
                    )

            except Exception as e:
                logger.error(f"Ошибка при клике по кнопке 'Войти с паролем': {e}")
                self.driver.save_screenshot("logs/login_password_button_error.png")
                return False

            # ШАГ 3: Ищем поле пароля сразу (форма должна загрузиться быстро)
            logger.debug("Шаг 3: Ищем поле пароля...")

            # Небольшая задержка для загрузки формы
            time.sleep(1)

            # ШАГ 4: Ввод пароля и нажатие "Войти"
            logger.debug("Шаг 4: Вводим пароль...")

            # Поиск поля пароля - пробуем сразу несколько методов
            password_input = None
            password_selectors = [
                'input[type="password"]',
                'input[data-qa="account-login-password"]',
                'input[autocomplete="current-password"]',
                'input.bloko-input[type="password"]',
                'input[placeholder*="парол"]',
                'input[placeholder*="Парол"]',
            ]

            # Сначала пробуем через JavaScript - самый быстрый способ
            try:
                password_input = self.driver.execute_script("""
                    var inputs = document.querySelectorAll('input');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].type === 'password') {
                            var style = window.getComputedStyle(inputs[i]);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                return inputs[i];
                            }
                        }
                    }
                    return null;
                """)
                if password_input:
                    logger.debug("Поле пароля найдено через JavaScript")
            except Exception as e:
                logger.debug(f"Ошибка при поиске через JavaScript: {e}")

            # Если не найдено через JS, пробуем через Selenium с коротким ожиданием
            if not password_input:
                try:
                    password_input = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'input[type="password"]')
                        )
                    )
                    logger.debug("Поле пароля найдено через Selenium")
                except Exception:
                    logger.debug(
                        "Поле пароля не найдено через Selenium, пробуем другие селекторы..."
                    )
                    password_input = self._find_element_by_multiple_selectors(
                        password_selectors, timeout=5
                    )

            # Если все еще не найдено, пробуем через JavaScript с более детальным поиском
            if not password_input:
                logger.debug("Пробуем найти поле пароля через JavaScript...")
                try:
                    password_input = self.driver.execute_script("""
                        // Ищем все input элементы
                        var inputs = document.querySelectorAll('input');
                        for (var i = 0; i < inputs.length; i++) {
                            var input = inputs[i];
                            // Проверяем тип password
                            if (input.type === 'password') {
                                // Проверяем, что элемент видимый
                                var style = window.getComputedStyle(input);
                                if (style.display !== 'none' && style.visibility !== 'hidden') {
                                    return input;
                                }
                            }
                        }
                        return null;
                    """)

                    if password_input:
                        logger.debug("Поле пароля найдено через JavaScript")
                    else:
                        # Пробуем найти по placeholder или другим атрибутам
                        password_input = self.driver.execute_script("""
                            var inputs = document.querySelectorAll('input');
                            for (var i = 0; i < inputs.length; i++) {
                                var input = inputs[i];
                                var placeholder = (input.placeholder || '').toLowerCase();
                                var name = (input.name || '').toLowerCase();
                                if (placeholder.includes('парол') || name.includes('password')) {
                                    var style = window.getComputedStyle(input);
                                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                                        return input;
                                    }
                                }
                            }
                            return null;
                        """)
                except Exception as e:
                    logger.debug(f"Ошибка при поиске через JavaScript: {e}")

            if not password_input:
                logger.error("Не удалось найти поле ввода пароля")
                logger.info("Текущий URL: " + self.driver.current_url)
                logger.info("Текущий заголовок страницы: " + self.driver.title)
                # Сохраняем HTML для отладки
                try:
                    page_source = self.driver.page_source[:5000]  # Первые 5000 символов
                    logger.debug(f"Начало HTML страницы: {page_source}")
                except Exception:
                    pass
                self.driver.save_screenshot("logs/login_step4_error.png")
                return False

            # Вводим пароль
            password_input.clear()
            password_input.send_keys(self.config.HH_PASSWORD)
            logger.debug("Пароль введен")
            time.sleep(1)

            # Поиск кнопки "Войти"
            login_button_selectors = [
                '//button[contains(text(), "Войти")]',
                'button[type="submit"]',
                'button[data-qa="account-login-submit"]',
                'button.bloko-button[type="submit"]',
            ]

            login_button = None
            for selector in login_button_selectors:
                try:
                    if selector.startswith("//"):
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    break
                except Exception:
                    continue

            if not login_button:
                logger.error("Не удалось найти кнопку 'Войти'")
                self.driver.save_screenshot("logs/login_step4_error.png")
                return False

            # Проверяем наличие капчи ПЕРЕД попыткой входа
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                if (
                    "капч" in page_text
                    or "робот" in page_text
                    or "captcha" in page_text
                ):
                    logger.warning("Обнаружена капча на странице входа!")
                    logger.warning("hh.ru требует подтверждение, что вы не робот.")
                    logger.warning("Это может произойти из-за частых попыток входа.")
                    logger.warning("РЕШЕНИЕ:")
                    logger.warning("1. Подождите 10-15 минут перед следующей попыткой")
                    logger.warning(
                        "2. Или войдите вручную через браузер один раз, чтобы 'разблокировать' аккаунт"
                    )
                    logger.warning("3. После этого бот должен работать нормально")
                    self.driver.save_screenshot("logs/captcha_detected.png")
                    return False
            except Exception:
                pass

            # Нажимаем кнопку "Войти"
            login_button.click()
            logger.debug("Кнопка 'Войти' нажата")

            # Ждем загрузки страницы после авторизации (увеличено время для надежности)
            logger.debug("Ожидаем завершения авторизации...")
            time.sleep(8)

            # Проверяем успешную авторизацию несколькими способами
            max_attempts = 5
            for attempt in range(max_attempts):
                current_url = self.driver.current_url
                logger.debug(
                    f"Попытка {attempt + 1}/{max_attempts}: Текущий URL: {current_url}"
                )

                # Проверка на капчу после попытки входа
                try:
                    page_text = self.driver.find_element(
                        By.TAG_NAME, "body"
                    ).text.lower()
                    if "капч" in page_text or (
                        "робот" in page_text and "подтвердите" in page_text
                    ):
                        logger.error("Обнаружена капча после попытки входа!")
                        logger.error("hh.ru требует подтверждение, что вы не робот.")
                        logger.error(
                            "Это произошло из-за частых попыток автоматического входа."
                        )
                        logger.error("РЕШЕНИЕ:")
                        logger.error(
                            "1. Подождите 10-15 минут перед следующей попыткой"
                        )
                        logger.error("2. Или войдите вручную через браузер один раз")
                        logger.error("3. После этого бот должен работать нормально")
                        self.driver.save_screenshot("logs/captcha_after_login.png")
                        return False
                except Exception:
                    pass

                # Способ 1: Проверка URL (не должен содержать account/login)
                if "account/login" not in current_url:
                    logger.success("Авторизация успешна (по URL)")
                    logger.debug(f"Текущий URL после авторизации: {current_url}")
                    self._is_logged_in = True
                    return True

                # Способ 2: Проверка наличия элементов личного кабинета
                try:
                    # Ищем элементы, которые появляются после успешного входа
                    personal_elements = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        '[data-qa="mainmenu_applicantResumes"], [data-qa="mainmenu_myResumes"], .supernova-navi-item, [href*="/applicant/resumes"]',
                    )
                    if personal_elements:
                        logger.success(
                            "Авторизация успешна (найдены элементы личного кабинета)"
                        )
                        logger.debug(f"Текущий URL: {current_url}")
                        self._is_logged_in = True
                        return True
                except Exception:
                    pass

                # Способ 3: Проверка на наличие ошибок
                try:
                    error_messages = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        '.bloko-form-error, .error, [data-qa="account-login-error"], .bloko-notification-error',
                    )
                    if error_messages:
                        for msg in error_messages:
                            error_text = msg.text.strip()
                            if error_text:
                                logger.error(f"Сообщение об ошибке: {error_text}")
                                # Если есть ошибка, не ждем дальше
                                self.driver.save_screenshot("logs/login_failed.png")
                                return False
                except Exception:
                    pass

                # Если еще не определили результат, ждем еще немного
                if attempt < max_attempts - 1:
                    time.sleep(2)

            # Если все попытки не удались
            logger.error("Авторизация не удалась - остались на странице входа")
            logger.debug(f"Финальный URL: {current_url}")
            self.driver.save_screenshot("logs/login_failed.png")

            # Попытка получить больше информации о странице
            try:
                page_title = self.driver.title
                logger.debug(f"Заголовок страницы: {page_title}")
                # Проверяем наличие текста на странице
                page_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                logger.debug(f"Начало текста страницы: {page_text[:200]}")

                # Финальная проверка на капчу
                if "капч" in page_text.lower() or (
                    "робот" in page_text.lower() and "подтвердите" in page_text.lower()
                ):
                    logger.error("Обнаружена капча на странице!")
                    logger.error("Подождите 10-15 минут или войдите вручную один раз.")
            except Exception:
                pass

            return False

        except InvalidSessionIdException as e:
            logger.error(f"Сессия браузера умерла при авторизации: {e}")
            self.restart_webdriver()
            self._kill_zombie_browsers()
            return False

        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            logger.exception("Детали ошибки:")
            if isinstance(e, (InvalidSessionIdException, WebDriverException)):
                self.restart_webdriver()
                self._kill_zombie_browsers()
            try:
                if self.driver and self._is_session_alive():
                    self.driver.save_screenshot("logs/login_error.png")
                    logger.info("Скриншот сохранен в logs/login_error.png")
            except Exception:
                pass
            return False

    def update_resume_via_web(self, resume_id: str = None) -> bool:
        """
        Поднятие резюме через веб-автоматизацию (Selenium)
        Имитирует действия пользователя в браузере
        """
        try:
            self._init_browser()

            # Авторизация
            if not self._login():
                return False

            # Определяем ID резюме для поднятия
            if not resume_id:
                resume_ids = self.config.get_resume_ids()
                if not resume_ids:
                    logger.error("Не указан ID резюме")
                    return False
                resume_id = resume_ids[0]

            # Переход на страницу резюме
            resume_url = f"{self.config.HH_BASE_URL}/resume/{resume_id}"
            logger.info(f"Переходим на страницу резюме: {resume_url}")
            self._get_url_with_retry(resume_url, attempts=2, desc="страницы резюме")
            time.sleep(3)

            # Сначала проверяем, не было ли резюме уже поднято сегодня
            logger.debug("Проверяем статус резюме...")
            self.driver.page_source.lower()

            # Ищем сообщения о том, когда можно поднять резюме
            can_update_info = self.driver.execute_script("""
                var text = document.body.textContent || document.body.innerText;
                var info = {
                    canUpdate: false,
                    message: ''
                };
                
                // Ищем информацию о времени следующего поднятия
                if (text.includes('можно сегодня') || text.includes('можно поднять')) {
                    var matches = text.match(/можно (сегодня|поднять)[^\\n]*\\d{1,2}:\\d{2}/i);
                    if (matches) {
                        info.message = matches[0];
                        info.canUpdate = false; // Уже поднято сегодня
                    }
                }
                
                // Ищем информацию о том, что резюме уже поднято
                if (text.includes('уже поднято') || text.includes('поднято сегодня')) {
                    info.canUpdate = false;
                    info.message = 'Резюме уже поднято сегодня';
                }
                
                return info;
            """)

            if can_update_info and can_update_info.get("message"):
                logger.info(
                    f"Информация о статусе резюме: {can_update_info['message']}"
                )
                if (
                    "можно сегодня" in can_update_info["message"].lower()
                    or "можно поднять" in can_update_info["message"].lower()
                ):
                    logger.info("Резюме уже было поднято сегодня. Цель достигнута!")
                    return True

            # Поиск кнопки "Поднять в поиске" или "Поднимать автоматически"
            logger.debug("Ищем кнопку для поднятия резюме...")

            css_selectors = [
                'button[data-qa="resume-update-button"]',
                'a[data-qa="resume-update-button"]',
                'button[data-qa="resume-update"]',
                'a[data-qa="resume-update"]',
                'button.bloko-button[data-qa*="update"]',
                'a.bloko-link[data-qa*="update"]',
            ]

            xpath_selectors = [
                '//button[contains(text(), "Поднять в поиске")]',
                '//a[contains(text(), "Поднять в поиске")]',
                '//button[contains(text(), "Поднять резюме")]',
                '//a[contains(text(), "Поднять резюме")]',
                '//button[contains(text(), "Поднимать автоматически")]',
                '//a[contains(text(), "Поднимать автоматически")]',
                '//*[contains(text(), "Поднять") and contains(text(), "поиске")]',
                '//*[contains(text(), "Поднять") and contains(text(), "резюме")]',
            ]

            update_button = None

            # Сначала пробуем CSS селекторы
            for selector in css_selectors:
                try:
                    update_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.debug(f"Кнопка найдена по CSS селектору: {selector}")
                    break
                except Exception:
                    continue

            # Если не нашли, пробуем XPath селекторы
            if not update_button:
                for selector in xpath_selectors:
                    try:
                        update_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        logger.debug(f"Кнопка найдена по XPath селектору: {selector}")
                        break
                    except Exception:
                        continue

            # Если не нашли, пробуем через JavaScript
            if not update_button:
                logger.debug("Попытка найти кнопку через JavaScript...")
                update_button = self.driver.execute_script("""
                    var elements = document.querySelectorAll('button, a, div[role="button"]');
                    for (var i = 0; i < elements.length; i++) {
                        var text = elements[i].textContent.trim();
                        if (text.includes('Поднять в поиске') || 
                            text.includes('Поднять резюме') ||
                            text.includes('Поднимать автоматически')) {
                            var style = window.getComputedStyle(elements[i]);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                return elements[i];
                            }
                        }
                    }
                    return null;
                """)

            if update_button:
                # Проверяем, не заблокирована ли кнопка
                is_disabled = self.driver.execute_script(
                    """
                    return arguments[0].disabled || 
                           arguments[0].classList.contains('disabled') ||
                           arguments[0].getAttribute('aria-disabled') === 'true';
                """,
                    update_button,
                )

                if is_disabled:
                    logger.warning(
                        "Кнопка 'Поднять в поиске' найдена, но заблокирована. Возможно, резюме уже было поднято сегодня."
                    )
                    return False

                # Прокручиваем к кнопке и кликаем
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                    update_button,
                )
                time.sleep(2)

                # Пробуем кликнуть через JavaScript, если обычный клик не работает
                try:
                    update_button.click()
                except Exception:
                    logger.debug(
                        "Обычный клик не сработал, пробуем через JavaScript..."
                    )
                    self.driver.execute_script("arguments[0].click();", update_button)

                logger.success(
                    f"Резюме {resume_id} успешно поднято через веб-интерфейс"
                )

                # Ждем подтверждения действия
                time.sleep(3)

                # Закрываем возможные всплывающие окна
                try:
                    close_buttons = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        '.bloko-modal-close-button, [data-qa="modal-close"], .bloko-modal__close',
                    )
                    for btn in close_buttons:
                        try:
                            btn.click()
                            time.sleep(1)
                        except Exception:
                            pass
                except Exception:
                    pass

                return True
            else:
                # Проверяем, есть ли сообщение о том, что резюме уже поднято
                logger.info(
                    "Кнопка 'Поднять в поиске' не найдена. Проверяем причину..."
                )

                # Ищем сообщения о том, что резюме уже поднято или когда можно поднять
                already_updated_messages = self.driver.execute_script("""
                    var messages = [];
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var text = elements[i].textContent || '';
                        if (text.includes('уже поднято') || 
                            text.includes('поднято сегодня') ||
                            text.includes('можно поднять') ||
                            text.includes('можно сегодня') ||
                            text.includes('доступно через') ||
                            (text.includes('можно') && text.includes('сегодня') && text.match(/\\d{1,2}:\\d{2}/))) {
                            messages.push(text.trim());
                        }
                    }
                    return messages;
                """)

                if already_updated_messages:
                    logger.info(f"Найдено сообщение: {already_updated_messages[0]}")
                    # Проверяем, есть ли информация о времени следующего поднятия
                    message_text = already_updated_messages[0].lower()
                    if (
                        "можно сегодня" in message_text
                        or "можно поднять" in message_text
                    ):
                        # Извлекаем время следующего поднятия
                        time_match = self.driver.execute_script(
                            """
                            var text = arguments[0];
                            var match = text.match(/\\d{1,2}:\\d{2}/);
                            return match ? match[0] : null;
                        """,
                            already_updated_messages[0],
                        )
                        if time_match:
                            logger.info(
                                f"Резюме уже было поднято сегодня. Следующее поднятие возможно в {time_match}"
                            )
                        else:
                            logger.info("Резюме уже было поднято сегодня.")
                        logger.info("Цель достигнута - резюме уже поднято!")
                        return True  # Возвращаем True, так как резюме уже поднято

                # Сохраняем скриншот для отладки
                try:
                    self.driver.save_screenshot("logs/resume_page_error.png")
                    logger.info(
                        "Скриншот страницы сохранен в logs/resume_page_error.png"
                    )
                except Exception:
                    pass

                logger.warning("Кнопка 'Поднять в поиске' не найдена. Возможно:")
                logger.warning("  1. Резюме уже было поднято сегодня")
                logger.warning("  2. Изменился интерфейс сайта hh.ru")
                logger.warning("  3. Резюме не активно или находится в архиве")
                return False

        except InvalidSessionIdException as e:
            logger.error(f"Сессия браузера умерла при поднятии резюме: {e}")
            self.restart_webdriver()
            self._kill_zombie_browsers()
            return False

        except Exception as e:
            logger.error(f"Ошибка при поднятии резюме через веб: {e}")
            logger.exception("Детали ошибки:")
            if isinstance(e, WebDriverException) and not self._is_session_alive():
                self.restart_webdriver()
                self._kill_zombie_browsers()
            try:
                if self.driver and self._is_session_alive():
                    self.driver.save_screenshot("logs/resume_update_error.png")
                    logger.info("Скриншот сохранен в logs/resume_update_error.png")
            except Exception:
                pass
            return False

    def update_resume(self, resume_id: str = None) -> bool:
        """
        Основной метод для поднятия резюме
        Пытается использовать API, если не получается - использует веб-автоматизацию

        Args:
            resume_id: ID резюме для поднятия. Если не указан, используется первый из списка.
        """
        # Определяем ID резюме для поднятия
        if not resume_id:
            resume_ids = self.config.get_resume_ids()
            if not resume_ids:
                logger.error("Не указаны ID резюме")
                return False
            resume_id = resume_ids[0]

        logger.info(f"Начинаем поднятие резюме {resume_id}...")

        # Сначала пробуем через API
        if self.config.HH_ACCESS_TOKEN:
            if self.update_resume_via_api(resume_id):
                return True
            logger.info("API метод не сработал, пробуем через веб-автоматизацию...")

        # Если API не доступен или не сработал, используем веб-автоматизацию
        if self.config.HH_LOGIN and self.config.HH_PASSWORD:
            return self.update_resume_via_web(resume_id)

        logger.error("Нет доступных методов для поднятия резюме")
        return False


if __name__ == "__main__":
    # Настройка логирования
    logger.add("logs/hh_bot_{time}.log", rotation="1 day", retention="7 days")

    # Проверка конфигурации
    errors = Config.validate()
    if errors:
        logger.error("Ошибки конфигурации:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.info(
            "Пожалуйста, создайте файл .env на основе .env.example и заполните его"
        )
        exit(1)

    # Запуск бота
    with HHResumeBot() as bot:
        success = bot.update_resume()
        if success:
            logger.success("Резюме успешно поднято!")
        else:
            logger.error("Не удалось поднять резюме")
