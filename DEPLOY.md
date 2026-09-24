# Инструкция по развертыванию на сервере

## Требования к серверу

- **ОС**: Ubuntu 22.04 ✅
- **Python**: 3.8+ (рекомендуется 3.10+)
- **RAM**: минимум 512 МБ + swap 2 ГБ; **рекомендуется 1 ГБ** для стабильной работы Chromium
- **Диск**: от 20 ГБ (рекомендуется 30 ГБ)

## Подготовка сервера

### 1. Подключение к серверу

```bash
ssh your-server
# или если используете прямой доступ:
# ssh root@your-server-ip
```

### 2. Обновление системы

```bash
apt update && apt upgrade -y
```

### 3. Установка Python и необходимых пакетов

```bash
# Установка Python и pip
apt install -y python3 python3-pip python3-venv

# Установка зависимостей для Selenium и Chrome
apt install -y wget curl unzip

# Установка зависимостей для headless Chrome
apt install -y \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils
```

### 4. Увеличение swap (ВАЖНО для серверов с 512 МБ RAM; при 1 ГБ RAM swap всё равно полезен)

Chrome требует много памяти при установке. Рекомендуется сначала увеличить swap:

```bash
# Проверка текущего swap
free -h

# Создание swap файла (2 ГБ)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Проверка
free -h

# Сделать постоянным (добавить в /etc/fstab)
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### 5. Установка Google Chrome

```bash
# Добавление репозитория Google Chrome (современный способ для Ubuntu 22.04+)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# Установка Chrome
apt update
apt install -y google-chrome-stable

# Проверка установки
google-chrome --version
```

**Альтернатива: Если Chrome не устанавливается из-за нехватки памяти, используйте Chromium:**

```bash
# Установка Chromium (более легкий вариант)
apt install -y chromium-browser chromium-chromedriver

# Проверка
chromium-browser --version
```

Если используете Chromium, в файле `.env` установите `BROWSER_TYPE=chromium` и обновите код для поддержки Chromium.

## Развертывание проекта

### 1. Создание директории для проекта

```bash
mkdir -p /opt/hh-bot
cd /opt/hh-bot
```

### 2. Загрузка проекта на сервер

**Вариант А: Через git (если проект в репозитории)**
```bash
apt install -y git
git clone <ваш_репозиторий> /opt/hh-bot
```

**Вариант Б: Через scp с локального компьютера**
На вашем локальном компьютере:
```bash
scp -r /path/to/project/HH.ru/* your-server:/opt/hh-bot/
# или если используете прямой доступ:
# scp -r /path/to/project/HH.ru/* root@your-server-ip:/opt/hh-bot/
```

**Вариант В: Через rsync (рекомендуется)**
На вашем локальном компьютере (из каталога проекта или с полным путём; **не пишите отдельно `ssh`** — rsync сам вызовет SSH для `your-server` из `~/.ssh/config`):
```bash
rsync -avz \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.env' --exclude '*.md' --exclude '.ruff_cache' \
  --exclude '.git' --exclude '.DS_Store' --exclude 'logs/' \
  /path/to/project/HH.ru/ your-server:/opt/hh-bot/
# или если используете прямой доступ:
# rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
#   /path/to/project/HH.ru/ root@your-server-ip:/opt/hh-bot/
```

### 3. Настройка виртуального окружения

```bash
cd /opt/hh-bot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Создание файла конфигурации

```bash
cp .env.example .env
nano .env  # или используйте vi
```

Заполните `.env` файл своими данными:
```env
HH_LOGIN=your_email@example.com
HH_PASSWORD=your_password

# Вариант 1: Одно резюме
RESUME_ID=your_resume_id

# Вариант 2: Несколько резюме (будут подниматься поочередно)
# RESUME_IDS=resume_id_1,resume_id_2,resume_id_3

SCHEDULE_TIME=09:00
HEADLESS_BROWSER=true
BROWSER_TYPE=chrome
```

### 5. Тестовый запуск

```bash
cd /opt/hh-bot
source venv/bin/activate
python hh_bot.py
```

Если все работает, можно настроить автозапуск.

## Настройка автозапуска через systemd

### 1. Создание systemd сервиса

```bash
nano /etc/systemd/system/hh-bot.service
```

Содержимое файла:
```ini
[Unit]
Description=HH.ru Resume Bot Scheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/hh-bot
Environment="PATH=/opt/hh-bot/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/hh-bot/venv/bin/python /opt/hh-bot/scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:/opt/hh-bot/logs/systemd.log
StandardError=append:/opt/hh-bot/logs/systemd_error.log

[Install]
WantedBy=multi-user.target
```

### 2. Активация и запуск сервиса

```bash
# Перезагрузка systemd
systemctl daemon-reload

# Включение автозапуска при загрузке системы
systemctl enable hh-bot.service

# Запуск сервиса
systemctl start hh-bot.service

# Проверка статуса
systemctl status hh-bot.service

# Просмотр логов
journalctl -u hh-bot.service -f
```

### 3. Управление сервисом

```bash
# Проверка статуса
systemctl status hh-bot.service

# Остановка
systemctl stop hh-bot.service

# Запуск
systemctl start hh-bot.service

# Перезапуск (после обновления кода)
systemctl restart hh-bot.service

# Просмотр логов в реальном времени
journalctl -u hh-bot.service -f

# Просмотр последних 50 строк логов
journalctl -u hh-bot.service -n 50

# Просмотр логов за сегодня
journalctl -u hh-bot.service --since today
```

## Альтернативный вариант: Использование screen/tmux

Если не хотите использовать systemd, можно запустить в screen:

```bash
# Установка screen
apt install -y screen

# Создание сессии
screen -S hh-bot

# В сессии screen:
cd /opt/hh-bot
source venv/bin/activate
python scheduler.py

# Отключение от сессии: Ctrl+A, затем D
# Подключение к сессии: screen -r hh-bot
```

## Проверка работы

### Проверка логов

```bash
# Логи планировщика
# Последний файл лога
ls -lt /opt/hh-bot/logs/scheduler_*.log | head -1

# Просмотр последних строк
tail -n 50 /opt/hh-bot/logs/scheduler_*.log

# Просмотр в реальном времени
tail -f /opt/hh-bot/logs/scheduler_*.log

# Логи бота
tail -f /opt/hh-bot/logs/hh_bot_*.log

# Логи systemd (если используете)
journalctl -u hh-bot.service -f
```

### Проверка процессов

```bash
# Проверка, что процесс запущен
ps aux | grep scheduler.py

# Проверка использования ресурсов
htop
```

## Возможные проблемы и решения

### Проблема: Chromium/Chrome падает с ReadTimeoutError

Основная причина — зомби-процессы Chromium забивают память на сервере.

**Решение:**

```bash
# Проверить память
free -h

# Перезапустить сервис
systemctl restart hh-bot.service
```

Бот с версии 1.4+ автоматически завершает зомби-процессы перед и после каждого запуска — мягко (SIGTERM, затем SIGKILL только если процесс не ответил). Ручной `pkill -9` не нужен и на практике вреден: резкий SIGKILL не даёт Chromium убрать свой временный профиль, из-за чего диск постепенно заполняется (см. раздел «Диск заполнен» ниже). Если всё же нужно вручную:

```bash
python3 -c "from browser_cleanup import kill_zombie_browsers; kill_zombie_browsers()"
```

### Проблема: Chrome не запускается в headless режиме

**Решение**: Убедитесь, что установлены все зависимости и Chrome запускается с правильными флагами. В коде уже настроен headless режим.

### Проблема: Недостаточно памяти при установке Chrome

**Решение 1: Увеличение swap (рекомендуется для серверов с 512 МБ RAM)**

```bash
# Проверка текущего swap
free -h

# Создание swap файла (2 ГБ)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Проверка
free -h

# Сделать постоянным (добавить в /etc/fstab)
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Теперь попробуйте установить Chrome снова
apt clean
apt install -y google-chrome-stable
```

**Решение 2: Использование Chromium (более легкий вариант)**

```bash
# Установка Chromium вместо Chrome
apt install -y chromium-browser chromium-chromedriver

# Проверка
chromium-browser --version
```

Затем в коде нужно будет изменить `BROWSER_TYPE=chromium` в `.env` файле.

**Решение 3: Ошибка «ChromeDriver only supports Chrome version X», браузер версии Y (SessionNotCreatedException)**

После автообновления Chromium (например snap) версия браузера может стать новее, чем версия закэшированного ChromeDriver. Бот с версии 1.2+ сам запрашивает драйвер под текущую версию браузера; если ошибка остаётся:

1. Очистите кэш webdriver-manager и перезапустите сервис:
   ```bash
   rm -rf /root/.wdm/
   rm -rf /opt/hh-bot/.wdm/
   rm -rf ~/.cache/selenium/
   systemctl restart hh-bot.service
   ```
2. Проверьте версии: `chromium-browser --version` и при следующем запуске бот скачает подходящий ChromeDriver.
3. При необходимости обновите код проекта (в нём передаётся версия браузера в ChromeDriverManager).

**Решение 4: Очистка кэша apt и повторная установка**

```bash
# Очистка кэша apt
apt clean
rm -rf /var/cache/apt/archives/*

# Повторная установка
apt update
apt install -y google-chrome-stable
```

### Проблема: SessionNotCreatedException — ChromeDriver supports Chrome X, browser is Y

Chromium (snap/apt) мог обновиться, а ChromeDriver в кэше остался старым. Сделайте:

```bash
rm -rf /root/.wdm/ /opt/hh-bot/.wdm/ ~/.cache/selenium/
systemctl restart hh-bot.service
```

После обновления кода бот сам запрашивает ChromeDriver под версию установленного браузера.

### Проблема: InvalidSessionIdException (браузер закрыл соединение)

Chromium упал или был убит — сессия Selenium стала недействительной. Частые причины: нехватка RAM, заполненный диск, зомби-процессы.

**Решение (бот 1.3+):** код пересоздаёт браузер при мёртвой сессии и повторяет попытку. Если ошибки повторяются:

```bash
free -h
df -h /
systemctl restart hh-bot.service
```

Заполненный диск — самая частая скрытая причина этой ошибки (см. раздел ниже: без места Chromium не может создать профиль и падает, что выглядит как `InvalidSessionIdException`, а не как ошибка нехватки места). Рекомендуется апгрейд до **1 ГБ RAM**.

### Проблема: Диск заполнен (No space left on device)

На VDS с Chromium (snap) `/tmp/snap-private-tmp/snap.chromium/tmp/` может разрастись до нескольких ГБ — это осиротевшие каталоги `org.chromium.Chromium.scoped_dir.*`, которые Chromium не удаляет за собой при SIGKILL. Не синхронизируйте `.git` на сервер через rsync.

**С версии 1.4+ бот убирает эти каталоги автоматически** перед каждым запуском (и принудительно, если свободного места меньше 2 ГБ) — это не должно повторяться. Проверить, накопилось ли что-то прямо сейчас:

```bash
ls -1d /tmp/snap-private-tmp/snap.chromium/tmp/org.chromium.Chromium.scoped_dir.* 2>/dev/null | wc -l
```

Если число растёт от запуска к запуску — значит автоматическая уборка не сработала (например, бот запущен без обновлённого кода или в системе иной путь snap-песочницы). Разовая ручная уборка:

```bash
python3 -c "from browser_cleanup import cleanup_chromium_temp_dirs; print(cleanup_chromium_temp_dirs(force=True))"
```

**Если место заняла не уборка Chromium — общая диагностика и очистка:**

```bash
df -h /
du -sh /* 2>/dev/null | sort -rh | head -10
du -sh /tmp/* 2>/dev/null | sort -rh | head -5
```

```bash
# Старые ревизии snap
snap set system refresh.retain=2
snap list --all | awk '/disabled/{system("snap remove " $1 " --revision=" $3)}'

# Журналы и кеш apt
journalctl --vacuum-size=50M
apt-get clean

# Лишнее в каталоге бота (на сервере .git не нужен)
rm -rf /opt/hh-bot/.git /opt/hh-bot/__pycache__

df -h /
```

Скриншоты ошибок (`logs/*.png`, старше 7 дней) и старые версии ChromeDriver в `~/.wdm` бот с версии 1.4+ убирает сам после каждого запуска — ручная чистка `find ... -delete` не требуется.

Если `apt-get clean` пишет про lock — проверьте зависший процесс: `ps aux | grep apt` и завершите его (`kill`), затем повторите.

### Проблема: Селекторы не работают

**Решение**: Интерфейс hh.ru мог измениться. Проверьте логи и обновите селекторы в коде.

### Проблема: Авторизация не работает

**Решение**: 
- Проверьте правильность данных в `.env`
- Убедитесь, что `HEADLESS_BROWSER=true`
- Проверьте логи на наличие ошибок

## Безопасность

1. **Защита файла .env**:
   ```bash
   chmod 600 /opt/hh-bot/.env
   ```

2. **Ограничение доступа к директории**:
   ```bash
   chmod 700 /opt/hh-bot
   ```

3. **Регулярное обновление системы**:
   ```bash
   apt update && apt upgrade -y
   ```

## Мониторинг

Рекомендуется настроить мониторинг:
- Проверка логов на ошибки
- Настройка уведомлений (email, Telegram и т.д.)
- Мониторинг использования ресурсов

## Обновление проекта

При обновлении кода **сначала сделайте резервную копию на сервере** (чтобы можно было откатиться), затем заливайте файлы.

```bash
# 0. На сервере: бэкап каталога бота (архив лучше хранить ВНЕ /opt/hh-bot, чтобы rsync его не трогал)
ssh your-server 'mkdir -p /root/hh-bot-backups && tar -czf /root/hh-bot-backups/hh-bot-$(date +%Y%m%d_%H%M).tar.gz -C /opt hh-bot'

# Если нужен меньший архив без venv (после отката: заново pip install -r requirements.txt в venv):
# ssh your-server 'tar -czf /root/hh-bot-backups/hh-bot-$(date +%Y%m%d_%H%M)-no-venv.tar.gz -C /opt --exclude=hh-bot/venv hh-bot'

# 1. Загрузка обновленного кода на сервер (с локального компьютера)
# ВАЖНО: исключаем .env чтобы не перезаписать серверную конфигурацию
cd /path/to/project/HH.ru
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
  --exclude '*.md' --exclude '.ruff_cache' \
  --exclude '.git' --exclude '.DS_Store' --exclude 'logs/' \
  . your-server:/opt/hh-bot/

# 2. На сервере: перезапустить сервис (сам завершит зависшие процессы браузера)
ssh your-server

# 3. Обновление зависимостей (если нужно)
cd /opt/hh-bot
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 4. Перезапуск сервиса
systemctl restart hh-bot.service

# 5. Проверка статуса
systemctl status hh-bot.service

# 6. Просмотр логов для проверки работы
tail -n 50 /opt/hh-bot/logs/scheduler_*.log
```

**Откат из бэкапа** (если что-то пошло не так): остановите сервис, распакуйте архив поверх `/opt` или замените каталог `hh-bot` содержимым из архива, снова `chmod 600 /opt/hh-bot/.env`, запустите сервис.

## Резервное копирование

Рекомендуется **перед каждым обновлением кода** делать снимок (см. шаг 0 в разделе «Обновление проекта»). Дополнительно имеет смысл хранить копию `.env` отдельно (без выкладывания в git).

```bash
# Полный бэкап каталога проекта на сервере (в домашний каталог root или в /root/hh-bot-backups)
mkdir -p /root/hh-bot-backups
tar -czf /root/hh-bot-backups/hh-bot-$(date +%Y%m%d).tar.gz -C /opt hh-bot
```

Старые архивы в `/opt/hh-bot/` (например `hh-bot-backup-*.tar.gz`) после следующих rsync не удаляются, пока нет `--delete`, но новые бэкапы удобнее складывать **снаружи** `/opt/hh-bot`, чтобы не смешивать с рабочими файлами.

## Итоговая информация

### Текущая конфигурация

- **Сервер**: VDS сервер (Ubuntu 22.04)
- **Браузер**: Chromium (snap версия)
- **Интервал запуска**: Каждые 5 часов
- **Расположение**: `/opt/hh-bot`
- **Сервис**: `hh-bot.service` (systemd)

### Важные моменты

1. **Время на сервере**: UTC (разница с Москвой: +3 часа)
2. **Планировщик**: Запускается каждые 5 часов с момента старта сервиса
3. **Логи**: Хранятся в `/opt/hh-bot/logs/` и ротируются ежедневно
4. **Автозапуск**: Включен через `systemctl enable hh-bot.service`

### Проверка работы

```bash
# Статус сервиса
systemctl status hh-bot.service

# Последние логи
journalctl -u hh-bot.service -n 50

# Логи планировщика
# Последний файл лога
ls -lt /opt/hh-bot/logs/scheduler_*.log | head -1

# Просмотр последних строк
tail -n 50 /opt/hh-bot/logs/scheduler_*.log
```

### Обновление проекта

1. Обновите код локально
2. Загрузите на сервер:
   ```bash
   rsync -avz \
     --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
     --exclude '.env' --exclude '*.md' --exclude '.ruff_cache' \
     --exclude '.git' --exclude '.DS_Store' --exclude 'logs/' \
     /path/to/project/HH.ru/ your-server:/opt/hh-bot/
   ```
3. Перезапустите сервис: `systemctl restart hh-bot.service`

