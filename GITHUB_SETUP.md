# Инструкция по загрузке проекта в GitHub

## ✅ Проверка перед загрузкой

### 1. Убедитесь, что все файлы на месте

```bash
# Проверка структуры проекта
ls -la
```

Должны быть:
- ✅ README.md
- ✅ DEPLOY.md
- ✅ MATERIALS.md
- ✅ CHANGELOG.md
- ✅ PROJECT_SUMMARY.md
- ✅ requirements.txt
- ✅ config.py
- ✅ hh_bot.py
- ✅ scheduler.py
- ✅ .env.example
- ✅ .gitignore

### 2. Проверьте .gitignore

Убедитесь, что `.gitignore` исключает:
- `.env` (с вашими учетными данными!)
- `logs/`
- `__pycache__/`
- `.venv/`
- `.idea/`

### 3. Убедитесь, что .env не попадет в репозиторий

```bash
# Проверка
git status | grep .env
```

Если `.env` показывается в статусе, убедитесь, что он в `.gitignore`.

## 📤 Загрузка в GitHub

### Вариант 1: Создание нового репозитория

1. **Создайте репозиторий на GitHub**
   - Зайдите на github.com
   - Нажмите "New repository"
   - Название: `hh-resume-bot` (или любое другое)
   - Описание: "Бот для автоматического поднятия резюме на hh.ru"
   - Выберите Public или Private
   - **НЕ** добавляйте README, .gitignore или лицензию (они уже есть)

2. **Добавьте файлы в git**
   ```bash
   cd /path/to/project/HH.ru
   
   # Добавление всех файлов (кроме тех, что в .gitignore)
   git add .
   
   # Проверка что будет загружено
   git status
   
   # Коммит
   git commit -m "Initial commit: HH.ru resume bot"
   
   # Добавление удаленного репозитория (замените URL на ваш)
   git remote add origin https://github.com/yourusername/hh-resume-bot.git
   
   # Загрузка в GitHub
   git push -u origin main
   ```

### Вариант 2: Если репозиторий уже создан

```bash
cd /path/to/project/HH.ru

# Добавление файлов
git add .

# Коммит
git commit -m "Initial commit: HH.ru resume bot"

# Загрузка
git push -u origin main
```

## 🔍 Проверка после загрузки

1. Зайдите на GitHub и проверьте, что все файлы загружены
2. Убедитесь, что `.env` **НЕ** загружен
3. Убедитесь, что `logs/` **НЕ** загружена
4. Проверьте, что `.env.example` загружен

## 📝 Что должно быть в репозитории

✅ **Должно быть:**
- Все `.py` файлы
- `requirements.txt`
- `README.md`
- `DEPLOY.md`
- `MATERIALS.md`
- `CHANGELOG.md`
- `PROJECT_SUMMARY.md`
- `.env.example`
- `.gitignore`

❌ **НЕ должно быть:**
- `.env` (с вашими учетными данными!)
- `logs/`
- `__pycache__/`
- `.venv/`
- `.idea/` (опционально, но лучше исключить)

## 🔄 Синхронизация с сервером

После загрузки в GitHub, для синхронизации с сервером:

### Вариант 1: Через git (рекомендуется)

```bash
# На сервере
cd /opt/hh-bot
git pull origin main

# Перезапуск сервиса
systemctl restart hh-bot.service
```

### Вариант 2: Через rsync (как сейчас)

```bash
# На локальном компьютере
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  /path/to/project/HH.ru/ your-server:/opt/hh-bot/
```

## 🎯 Итоговая команда для загрузки

```bash
cd /path/to/project/HH.ru

# Проверка статуса
git status

# Добавление файлов
git add .

# Проверка что будет загружено (убедитесь, что .env НЕ в списке!)
git status

# Коммит
git commit -m "Initial commit: HH.ru resume bot - автоматическое поднятие резюме"

# Если репозиторий еще не создан, создайте его на GitHub, затем:
git remote add origin https://github.com/yourusername/your-repo-name.git
git branch -M main
git push -u origin main
```

---

**Важно:** Никогда не загружайте `.env` файл в публичный репозиторий! Он содержит ваши учетные данные.

