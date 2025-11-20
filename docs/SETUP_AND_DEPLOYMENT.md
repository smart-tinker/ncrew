# ⚙️ Установка и развертывание NeuroCrew Lab

## Системные требования

### Общие требования

- **Python 3.10+** - основной язык разработки
- **Операционная система:** Linux (рекомендуется), macOS, Windows
- **Память:** минимум 2GB RAM, рекомендуется 4GB+
- **Дисковое пространство:** минимум 1GB свободного места
- **Интернет-соединение:** для доступа к AI-сервисам

### Требования к AI-инструментам

#### Node.js (для OpenCode, Qwen)
```bash
# Требуется версия 20+
node --version  # v20.x.x
npm --version   # 10.x.x
```

#### Go (для Gemini)
```bash
# Требуется версия 1.21+
go version  # go version go1.21.x
```

#### Python пакеты (устанавливаются автоматически)
```bash
pip install -r requirements.txt
```

## Установка

### 1. Клонирование репозитория

```bash
# Клонирование
git clone https://github.com/your-org/ncrew.git
cd ncrew

# Проверка ветки
git checkout docs/align-docs-ncrew
```

### 2. Создание виртуального окружения

#### Рекомендуемый способ (через скрипт)
```bash
# Автоматическая настройка окружения
./ncrew.sh

# Скрипт выполнит:
# - Создание .venv
# - Установку зависимостей
# - Настройку переменных окружения
```

#### Ручная настройка
```bash
# Создание виртуального окружения
python3 -m venv .venv

# Активация
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

```bash
# Копирование шаблона
cp .env.example .env

# Редактирование конфигурации
nano .env  # или ваш любимый редактор
```

#### Обязательные переменные

```bash
# Основная конфигурация
MAIN_BOT_TOKEN=1234567890:ABCDEF...              # Токен listener-бота
TARGET_CHAT_ID=-1001234567890                    # ID целевого чата

# Веб-интерфейс
WEB_ADMIN_USER=admin
WEB_ADMIN_PASS=your_secure_password

# Настройки логирования
LOG_LEVEL=INFO
DATA_DIR=./data
```

#### Токены для actor-ботов (для каждой роли)

```bash
# Примеры для ролей из roles/agents.yaml
SOFTWARE_DEV_BOT_TOKEN=1234567890:GHIJKL...
CODE_REVIEW_BOT_TOKEN=1234567890:LMNOPQ...
PRODUCT_OWNER_BOT_TOKEN=1234567890:RSTUVW...
SENIOR_ARCHITECT_BOT_TOKEN=1234567890:XYZABC...
PRODUCT_ANALYST_BOT_TOKEN=1234567890:DEFGHI...
SECURITY_ANALYST_BOT_TOKEN=1234567890:JKLMNOP...
DEVOPS_SENIOR_BOT_TOKEN=1234567890:QRSTUVW...
SDET_SENIOR_BOT_TOKEN=1234567890:WXYZAB...
SCRUM_MASTER_BOT_TOKEN=1234567890:BCDEFG...
SYSTEM_ANALYST_BOT_TOKEN=1234567890:HIJKLMN...
```

#### Опциональные переменные

```bash
# Таймауты и ограничения
AGENT_TIMEOUT=300                    # Таймаут выполнения роли (секунды)
MAX_CONVERSATION_LENGTH=100          # Максимальная длина диалога
GEMINI_MAX_TIMEOUTS=3               # Максимальное количество таймаутов Gemini

# Системные настройки
SYSTEM_REMINDER_INTERVAL=3600       # Интервал напоминаний (секунды)
CLEANUP_BACKUP_DAYS=7               # Дни хранения бэкапов
```

### 4. Настройка AI-инструментов

#### OpenCode

```bash
# Установка
curl -fsSL https://opencode.ai/install | bash
# или
npm i -g opencode-ai@latest

# Аутентификация
opencode auth login

# Проверка
opencode --version
opencode acp --help
```

#### Qwen

```bash
# Установка
npm install -g @qwen-code/qwen-code@0.1.4

# Первоначальный запуск для OAuth
qwen

# Проверка ACP
qwen --experimental-acp --help
```

#### Gemini

```bash
# Установка
go install github.com/google/gemini-cli@latest

# Настройка конфигурации
mkdir -p ~/.gemini
cat > ~/.gemini/settings.json << EOF
{
  "model": "gemini-pro",
  "experimental_acp": true
}
EOF

# Аутентификация через gcloud (если требуется)
gcloud auth application-default login

# Проверка
gemini --version
gemini --experimental-acp --help
```

#### Codex

```bash
# Установка
npm install -g @openai/codex

# Аутентификация (требуется платная подписка)
codex login

# Проверка
codex --version
codex exec --json "ping"
```

#### Claude Code

```bash
# Установка
curl -fsSL https://claude.ai/install.sh | bash
# или
npm install -g @anthropic-ai/claude-code

# Настройка токена (требуется платная подписка)
claude setup-token

# Проверка
claude --version
claude -p "ping"
```

### 5. Настройка Telegram

#### Создание ботов через @BotFather

1. **Listener Bot:**
   ```
   /newbot
   NeuroCrew Listener
   ncrew_listener_bot
   ```
   - Сохраните токен в `MAIN_BOT_TOKEN`

2. **Actor Bots** (для каждой роли):
   ```
   /newbot
   Software Developer Bot
   software_dev_bot
   ```
   - Повторите для каждой роли из `roles/agents.yaml`
   - Сохраните токены в соответствующие переменные окружения

#### Настройка Telegram-группы

1. **Создание группы:**
   - Создайте новую группу в Telegram
   - Добавьте listener-бота в группу
   - Добавьте всех actor-ботов в группу
   - Добавьте участников

2. **Отключение Privacy Mode для listener-бота:**
   ```
   @BotFather → /mybots → NeuroCrew Listener → Bot Settings → Group Privacy → Turn off
   ```

3. **Получение Chat ID:**
   - Отправьте любое сообщение в группу
   - Перешлите это сообщение @userinfobot
   - Скопируйте `Chat ID` в `TARGET_CHAT_ID`

4. **Проверка прав:**
   - Убедитесь, что все боты могут отправлять сообщения
   - Проверьте, что listener-бот может читать сообщения

## Запуск

### Базовый запуск

```bash
# Запуск основного приложения
python main.py

# Ожидаемый вывод:
# 2023-11-20 14:30:22 INFO main - NeuroCrew Lab starting...
# 2023-11-20 14:30:22 INFO main - Telegram bot initialized
# 2023-11-20 14:30:22 INFO main - Web server started on port 8080
# 2023-11-20 14:30:22 INFO main - NeuroCrew Lab ready
```

### Запуск с отладкой

```bash
# Подробное логирование
LOG_LEVEL=DEBUG python main.py

# Логирование в файл
LOG_LEVEL=DEBUG python main.py 2>&1 | tee ncrew.log
```

### Запуск только веб-сервера

```bash
# Для независимой работы веб-интерфейса
python app/interfaces/web_server.py
```

### Проверка работоспособности

```bash
# Проверка конфигурации
python scripts/validate_system.py

# Проверка доступности агентов
python scripts/validate_agents.py

# Комплексная диагностика
python scripts/troubleshoot.py
```

## Docker развертывание

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    git \
    nodejs \
    npm \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

# Установка AI-инструментов
RUN npm install -g @openai/codex
RUN npm install -g @qwen-code/qwen-code@0.1.4
RUN go install github.com/google/gemini-cli@latest

# Настройка рабочего окружения
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Создание необходимых директорий
RUN mkdir -p data/conversations data/logs data/backups

# Настройка прав
RUN chmod +x ncrew.sh

# Порт для веб-сервера
EXPOSE 8080

# Запуск
CMD ["python", "main.py"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  ncrew:
    build: .
    container_name: neurocrew-lab
    restart: unless-stopped
    environment:
      - LOG_LEVEL=INFO
      - DATA_DIR=/app/data
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./roles:/app/roles
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Запуск через Docker

```bash
# Сборка образа
docker build -t neurocrew-lab .

# Запуск с docker-compose
docker-compose up -d

# Проверка логов
docker-compose logs -f ncrew

# Остановка
docker-compose down
```

## Производственное развертывание

### Systemd сервис

#### Создание сервиса

```bash
sudo nano /etc/systemd/system/neurocrew-lab.service
```

```ini
[Unit]
Description=NeuroCrew Lab AI Orchestration Platform
After=network.target

[Service]
Type=simple
User=ncrew
Group=ncrew
WorkingDirectory=/opt/neurocrew-lab
Environment=PATH=/opt/neurocrew-lab/.venv/bin
EnvironmentFile=/opt/neurocrew-lab/.env
ExecStart=/opt/neurocrew-lab/.venv/bin/python main.py
Restart=always
RestartSec=10

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocrew-lab

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/neurocrew-lab/data

[Install]
WantedBy=multi-user.target
```

#### Управление сервисом

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable neurocrew-lab

# Запуск
sudo systemctl start neurocrew-lab

# Проверка статуса
sudo systemctl status neurocrew-lab

# Просмотр логов
sudo journalctl -u neurocrew-lab -f

# Перезапуск
sudo systemctl restart neurocrew-lab

# Остановка
sudo systemctl stop neurocrew-lab
```

### Nginx反向代理

#### Конфигурация Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Перенаправление на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL конфигурация
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    # Безопасность
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Веб-интерфейс
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Ограничение доступа к API
    location /api {
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        allow 192.168.0.0/16;
        deny all;
        
        proxy_pass http://127.0.0.1:8080;
    }
}
```

### Мониторинг

#### Prometheus метрики

```python
# Добавление в main.py
from prometheus_client import start_http_server, Counter, Histogram

# Метрики
message_counter = Counter('ncrew_messages_total', 'Total messages processed', ['role'])
response_time = Histogram('ncrew_response_time_seconds', 'Response time in seconds')

# Запуск Prometheus сервера
start_http_server(8000)
```

#### Grafana дашборд

```json
{
  "dashboard": {
    "title": "NeuroCrew Lab Monitoring",
    "panels": [
      {
        "title": "Messages per Role",
        "type": "stat",
        "targets": [
          {
            "expr": "sum by (role) (rate(ncrew_messages_total[5m]))"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(ncrew_response_time_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

## Резервное копирование и восстановление

### Резервное копирование

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/neurocrew-lab"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="ncrew_backup_${DATE}"

# Создание директории
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

# Копирование данных
cp -r /opt/neurocrew-lab/data "${BACKUP_DIR}/${BACKUP_NAME}/"
cp /opt/neurocrew-lab/.env "${BACKUP_DIR}/${BACKUP_NAME}/"
cp -r /opt/neurocrew-lab/roles "${BACKUP_DIR}/${BACKUP_NAME}/"

# Архивирование
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" "${BACKUP_NAME}"

# Удаление временной директории
rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

# Удаление старых бэкапов (оставляем последние 7)
find "${BACKUP_DIR}" -name "ncrew_backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
```

### Восстановление

```bash
#!/bin/bash
# restore.sh

BACKUP_FILE=$1
RESTORE_DIR="/tmp/ncrew_restore"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

# Распаковка
mkdir -p "$RESTORE_DIR"
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# Остановка сервиса
sudo systemctl stop neurocrew-lab

# Восстановление данных
sudo cp -r "${RESTORE_DIR}"/*/data/* /opt/neurocrew-lab/data/
sudo cp "${RESTORE_DIR}"*/.env /opt/neurocrew-lab/
sudo cp -r "${RESTORE_DIR}"*/roles/* /opt/neurocrew-lab/roles/

# Установка прав
sudo chown -R ncrew:ncrew /opt/neurocrew-lab/

# Запуск сервиса
sudo systemctl start neurocrew-lab

# Очистка
rm -rf "$RESTORE_DIR"

echo "Restore completed"
```

## Автоматическое обновление

### Скрипт обновления

```bash
#!/bin/bash
# update.sh

set -e

BACKUP_DIR="/backup/neurocrew-lab"
DATE=$(date +%Y%m%d_%H%M%S)

echo "Starting NeuroCrew Lab update..."

# Создание бэкапа
echo "Creating backup..."
./backup.sh

# Переключение на новую версию
echo "Updating code..."
cd /opt/neurocrew-lab
git fetch origin
git checkout main
git pull origin main

# Обновление зависимостей
echo "Updating dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

# Выполнение миграций (если нужны)
echo "Running migrations..."
# python scripts/migrate.py

# Перезапуск сервиса
echo "Restarting service..."
sudo systemctl restart neurocrew-lab

# Проверка работоспособности
echo "Checking health..."
sleep 10
if curl -f http://localhost:8080/health; then
    echo "Update completed successfully!"
else
    echo "Update failed! Rolling back..."
    # Логика отката
    exit 1
fi
```

### Cron для автоматического обновления

```bash
# Ежедневное обновление в 3:00
0 3 * * * /opt/neurocrew-lab/scripts/update.sh >> /var/log/ncrew-update.log 2>&1
```

## Траблшутинг

### Проверка системных требований

```bash
#!/bin/bash
# check_system.sh

echo "=== System Check ==="

# Python
python_version=$(python3 --version 2>&1)
echo "Python: $python_version"

# Node.js
node_version=$(node --version 2>&1)
echo "Node.js: $node_version"

# Go
go_version=$(go version 2>&1)
echo "Go: $go_version"

# Память
memory=$(free -h | grep "Mem:" | awk '{print $2}')
echo "Memory: $memory"

# Дисковое пространство
disk=$(df -h / | tail -1 | awk '{print $4}')
echo "Disk space: $disk"

# AI инструменты
echo ""
echo "=== AI Tools ==="

which opencode && opencode --version || echo "OpenCode: NOT FOUND"
which qwen && qwen --version || echo "Qwen: NOT FOUND"
which gemini && gemini --version || echo "Gemini: NOT FOUND"
which codex && codex --version || echo "Codex: NOT FOUND"
which claude && claude --version || echo "Claude: NOT FOUND"
```

### Диагностика проблем

```bash
#!/bin/bash
# diagnose.sh

echo "=== NeuroCrew Lab Diagnostics ==="

# Проверка конфигурации
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found"
else
    echo "✅ .env file exists"
    
    # Проверка обязательных переменных
    source .env
    
    if [ -z "$MAIN_BOT_TOKEN" ]; then
        echo "ERROR: MAIN_BOT_TOKEN not set"
    else
        echo "✅ MAIN_BOT_TOKEN set"
    fi
    
    if [ -z "$TARGET_CHAT_ID" ]; then
        echo "ERROR: TARGET_CHAT_ID not set"
    else
        echo "✅ TARGET_CHAT_ID set"
    fi
fi

# Проверка ролей
if [ ! -f "roles/agents.yaml" ]; then
    echo "ERROR: roles/agents.yaml not found"
else
    echo "✅ roles/agents.yaml exists"
fi

# Проверка директорий
for dir in data data/conversations data/logs data/backups; do
    if [ ! -d "$dir" ]; then
        echo "ERROR: Directory $dir not found"
        mkdir -p "$dir"
        echo "✅ Created directory $dir"
    else
        echo "✅ Directory $dir exists"
    fi
done

# Проверка прав
if [ ! -w "data" ]; then
    echo "ERROR: No write permissions to data directory"
else
    echo "✅ Write permissions to data directory"
fi
```