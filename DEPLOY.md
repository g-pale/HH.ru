# Инструкция по развертыванию на сервере

## Требования к серверу

- **ОС**: Ubuntu 22.04 (как у вас) ✅
- **Python**: 3.8+ (рекомендуется 3.10+)
- **RAM**: минимум 512 МБ (у вас есть) ✅
- **Диск**: достаточно места для Python, Chrome и зависимостей (~500 МБ)

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

### 4. Увеличение swap (ВАЖНО для серверов с 512 МБ RAM)

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
На вашем локальном компьютере:
```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
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
RESUME_ID=your_resume_id
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

**Решение 3: Очистка кэша и повторная установка**

```bash
# Очистка кэша apt
apt clean
rm -rf /var/cache/apt/archives/*

# Повторная установка
apt update
apt install -y google-chrome-stable
```

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

При обновлении кода:

```bash
# 1. Загрузка обновленного кода на сервер (с локального компьютера)
# На вашем локальном компьютере:
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  /path/to/project/HH.ru/ your-server:/opt/hh-bot/

# 2. На сервере: обновление зависимостей (если нужно)
ssh your-server
cd /opt/hh-bot
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 3. Перезапуск сервиса
systemctl restart hh-bot.service

# 4. Проверка статуса
systemctl status hh-bot.service

# 5. Просмотр логов для проверки работы
journalctl -u hh-bot.service -f
```

## Резервное копирование

Рекомендуется регулярно делать бэкап:
- Файл `.env` (с учетными данными)
- Логи
- Код проекта

```bash
# Создание бэкапа
tar -czf hh-bot-backup-$(date +%Y%m%d).tar.gz /opt/hh-bot
```

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
tail -n 50 /opt/hh-bot/logs/scheduler_*.log
```

### Обновление проекта

1. Обновите код локально
2. Загрузите на сервер: `rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' /path/to/project/HH.ru/ your-server:/opt/hh-bot/`
3. Перезапустите сервис: `systemctl restart hh-bot.service`

