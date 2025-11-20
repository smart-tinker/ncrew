# 🌐 Веб-сервер NeuroCrew Lab

## Обзор

Веб-сервер предоставляет **минимальную панель управления** для редактирования ролей и токенов через браузер. Реализован на Flask с Basic Auth аутентификацией и запускается в отдельном потоке от основного приложения.

## Архитектура

### Компоненты

```
Flask Web Server (app/interfaces/web_server.py)
├── Basic Auth Middleware
├── YAML Editor (roles/agents.yaml)
├── .env Editor (токены и переменные)
├── Role Validator
├── Bot Name Sanitizer
└── Reload Trigger (.reload flag)
```

### Файлы

- **`app/interfaces/web_server.py`** - основной Flask-приложение
- **`templates/index.html`** - веб-форма редактирования
- **`roles/agents.yaml`** - конфигурация ролей
- **`.env`** - переменные окружения и токены
- **`.reload`** - флаг перезапуска сервиса

## Доступ к панели

### URL и порт

```
http://localhost:8080
```

### Аутентификация

```bash
# .env файл
WEB_ADMIN_USER=admin
WEB_ADMIN_PASS=secure_password
```

### Запуск сервера

#### Автоматический запуск (рекомендуется)
```bash
python main.py
# Flask запускается автоматически в отдельном потоке
```

#### Ручной запуск
```bash
python app/interfaces/web_server.py
# Для отладки или независимой работы
```

## Функциональность

### Редактор ролей

#### Поля роли

| Поле | Обязательное | Описание | Пример |
|------|--------------|----------|--------|
| `role_name` | ✅ | Уникальный идентификатор роли | `software_developer` |
| `display_name` | ✅ | Отображаемое имя | `"Software Developer"` |
| `telegram_bot_name` | ✅ | Имя Telegram-бота | `Software_Dev_Bot` |
| `system_prompt_file` | ✅ | Путь к файлу промпта | `roles/prompts/software_developer.md` |
| `agent_type` | ✅ | Тип коннектора | `gemini_acp` |
| `cli_command` | ✅ | CLI команда агента | `gemini --experimental-acp` |
| `description` | ❌ | Описание роли | `"Старший разработчик"` |
| `is_moderator` | ❌ | Права модератора | `true` |

#### Валидация ролей

- **Уникальность `role_name`** - проверка дубликатов
- **Корректность `agent_type`** - проверка наличия коннектора
- **Валидность CLI команды** - базовая проверка синтаксиса
- **Существование промпт-файла** - проверка файловой системы
- **Формат имени бота** - авто-коррекция и санитизация

#### Санитизация имен ботов

```python
def _sanitize_bot_name(role_name: str) -> str:
    """Нормализация имени бота из роли."""
    # Удаление спецсимволов
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", role_name.strip())
    # Добавление суффикса _Bot
    if not candidate.lower().endswith("_bot"):
        candidate += "_Bot"
    return candidate
```

### Редактор токенов

#### Поддерживаемые переменные

```bash
# Telegram токены
MAIN_BOT_TOKEN=1234567890:ABCDEF...
SOFTWARE_DEV_BOT_TOKEN=1234567890:GHIJKL...
CODE_REVIEW_BOT_TOKEN=1234567890:LMNOPQ...

# Системные переменные
TARGET_CHAT_ID=-1001234567890
WEB_ADMIN_USER=admin
WEB_ADMIN_PASS=secure_password

# Настройки
LOG_LEVEL=INFO
AGENT_TIMEOUT=300
MAX_CONVERSATION_LENGTH=100
```

#### Валидация токенов

- **Формат Telegram токена** - проверка формата `数字:字符串`
- **Целочисленные значения** - для `TARGET_CHAT_ID`
- **Строковые значения** - для пользовательских настроек

## API эндпоинты

### GET /
**Описание:** Главная страница с формой редактирования
**Аутентификация:** Basic Auth
**Ответ:** HTML форма с текущими значениями

```python
@app.route('/')
@auth_required
def index():
    roles = load_roles_from_yaml()
    env_vars = load_env_vars()
    return render_template('index.html', roles=roles, env_vars=env_vars)
```

### POST /save
**Описание:** Сохранение изменений в ролях и переменных
**Аутентификация:** Basic Auth
**Тело:** Form data с полями ролей и env-переменных
**Ответ:** JSON с результатом сохранения

```python
@app.route('/save', methods=['POST'])
@auth_required
def save():
    try:
        # Валидация и сохранение ролей
        roles = validate_and_save_roles(request.form)
        
        # Валидация и сохранение env-переменных
        env_vars = validate_and_save_env(request.form)
        
        # Создание флага перезапуска
        create_reload_flag()
        
        return jsonify({"success": True, "message": "Сохранено успешно"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
```

### GET /health
**Описание:** Проверка состояния сервера
**Аутентификация:** Нет
**Ответ:** JSON со статусом

```python
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    })
```

## Работа с .reload флагом

### Назначение

Файл `.reload` сигнализирует основному приложению о необходимости перезагрузки конфигурации без перезапуска всего процесса.

### Создание флага

```python
def create_reload_flag():
    """Создание флага перезапуска."""
    reload_file = Path(".reload")
    reload_file.touch()
    logger.info("Reload flag created")
```

### Обработка в основном приложении

```python
# В main.py
async def check_reload_flag():
    """Проверка флага перезапуска."""
    reload_file = Path(".reload")
    if reload_file.exists():
        reload_file.unlink()  # Удаление флага
        await reload_configuration()  # Перезагрузка конфигурации
```

### Автоматическая перезагрузка

```python
# Периодическая проверка (каждые 30 секунд)
async def periodic_reload_check():
    while True:
        await check_reload_flag()
        await asyncio.sleep(30)
```

## Безопасность

### Basic Auth

```python
def check_auth(username, password):
    """Проверка учетных данных."""
    return (username == Config.WEB_ADMIN_USER and 
            password == Config.WEB_ADMIN_PASS)

def auth_required(f):
    """Декоратор для требуемой аутентификации."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Could not verify your access level for that URL.\n"
                "You have to login with proper credentials", 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated
```

### Валидация входных данных

#### YAML валидация

```python
def validate_roles_data(roles_data):
    """Валидация данных ролей."""
    errors = []
    
    for role in roles_data:
        # Проверка обязательных полей
        required_fields = ['role_name', 'display_name', 'telegram_bot_name', 
                          'system_prompt_file', 'agent_type', 'cli_command']
        
        for field in required_fields:
            if not role.get(field):
                errors.append(f"Поле {field} обязательно для роли {role.get('role_name', 'Unknown')}")
        
        # Проверка уникальности role_name
        role_names = [r['role_name'] for r in roles_data]
        if len(role_names) != len(set(role_names)):
            errors.append("role_name должны быть уникальными")
    
    return errors
```

#### Environment переменные

```python
def validate_env_var(key, value):
    """Валидация environment переменной."""
    if key.endswith('_TOKEN'):
        # Проверка формата Telegram токена
        if not re.match(r'^\d+:[A-Za-z0-9_-]+$', value):
            raise ValueError(f"Неверный формат токена для {key}")
    
    elif key == 'TARGET_CHAT_ID':
        # Проверка формата chat ID
        if not value.startswith('-') or not value[1:].isdigit():
            raise ValueError("TARGET_CHAT_ID должен быть отрицательным числом")
    
    return True
```

### Защита от CSRF

```python
# Простая CSRF защита через сессию
@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            abort(403)

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token
```

## Шаблонизация

### Структура templates/index.html

```html
<!DOCTYPE html>
<html>
<head>
    <title>NeuroCrew Lab - Управление ролями</title>
    <style>
        /* CSS стили */
    </style>
</head>
<body>
    <h1>🤖 NeuroCrew Lab - Управление ролями</h1>
    
    <!-- Форма редактирования ролей -->
    <form method="post" action="/save">
        <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
        
        <!-- Таблица ролей -->
        <table id="roles-table">
            <!-- Динамически генерируемые строки ролей -->
        </table>
        
        <!-- Environment переменные -->
        <fieldset>
            <legend>Environment Variables</legend>
            <!-- Динамически генерируемые поля env -->
        </fieldset>
        
        <button type="submit">💾 Сохранить изменения</button>
    </form>
    
    <script>
        // JavaScript для динамического управления формой
    </script>
</body>
</html>
```

### Динамические элементы

#### Добавление новой роли

```javascript
function addRole() {
    const roleIndex = document.querySelectorAll('.role-row').length;
    const roleRow = document.createElement('tr');
    roleRow.className = 'role-row';
    roleRow.innerHTML = `
        <td><input type="text" name="roles[${roleIndex}][role_name]" required></td>
        <td><input type="text" name="roles[${roleIndex}][display_name]" required></td>
        <td><input type="text" name="roles[${roleIndex}][telegram_bot_name]" required></td>
        <td><input type="text" name="roles[${roleIndex}][system_prompt_file]" required></td>
        <td>
            <select name="roles[${roleIndex}][agent_type]" required>
                <option value="gemini_acp">Gemini ACP</option>
                <option value="opencode_acp">OpenCode ACP</option>
                <option value="qwen_acp">Qwen ACP</option>
                <option value="codex_cli">Codex CLI</option>
                <option value="claude_cli">Claude CLI</option>
            </select>
        </td>
        <td><input type="text" name="roles[${roleIndex}][cli_command]" required></td>
        <td><input type="text" name="roles[${roleIndex}][description]"></td>
        <td><input type="checkbox" name="roles[${roleIndex}][is_moderator]"></td>
        <td><button type="button" onclick="removeRole(this)">❌</button></td>
    `;
    document.getElementById('roles-table').appendChild(roleRow);
}
```

#### Автозаполнение имени бота

```javascript
function autoFillBotName(input, index) {
    const roleName = input.value;
    const botNameInput = document.querySelector(`input[name="roles[${index}][telegram_bot_name]"]`);
    
    if (botNameInput && !botNameInput.value) {
        // Автоматическая генерация имени бота
        const botName = roleName
            .replace(/[^A-Za-z0-9_]+/g, '_')
            .toLowerCase() + '_bot';
        botNameInput.value = botName;
    }
}
```

## Интеграция с основным приложением

### Запуск в отдельном потоке

```python
# В main.py
def run_web_server():
    """Запуск Flask-сервера в отдельном потоке."""
    from app.interfaces.web_server import app
    
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=False,
        use_reloader=False
    )

# Запуск потока
web_thread = Thread(target=run_web_server, daemon=True)
web_thread.start()
```

### Graceful shutdown

```python
async def shutdown_web_server():
    """Корректное завершение работы веб-сервера."""
    # Отправка SIGTERM для Flask
    os.kill(os.getpid(), signal.SIGTERM)
```

## Логирование и мониторинг

### Структурированное логирование

```python
import logging
from app.utils.logger import get_logger

logger = get_logger("WebServer")

@app.route('/save', methods=['POST'])
@auth_required
def save():
    logger.info("Configuration save attempt", extra={
        "remote_addr": request.remote_addr,
        "user_agent": request.headers.get('User-Agent'),
        "roles_count": len(request.form.getlist('roles'))
    })
    
    try:
        # Сохранение конфигурации
        logger.info("Configuration saved successfully")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Configuration save failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

### Метрики

- `web_requests_total` - количество HTTP запросов
- `web_save_attempts` - попыток сохранения конфигурации
- `web_save_errors` - ошибок сохранения
- `web_auth_failures` - неудачных попыток аутентификации

### Health checks

```python
@app.route('/health')
def health():
    """Проверка состояния веб-сервера."""
    checks = {
        "database": check_yaml_access(),
        "filesystem": check_filesystem_permissions(),
        "memory": check_memory_usage()
    }
    
    status = "healthy" if all(checks.values()) else "unhealthy"
    
    return jsonify({
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    })
```

## Тестирование

### Unit-тесты

```python
import pytest
from unittest.mock import Mock, patch
from app.interfaces.web_server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_unauthorized(client):
    """Тест доступа без аутентификации."""
    response = client.get('/')
    assert response.status_code == 401

def test_index_authorized(client):
    """Тест доступа с аутентификацией."""
    headers = {'Authorization': 'Basic YWRtaW46c2VjdXJlX3Bhc3N3b3Jk'}
    response = client.get('/', headers=headers)
    assert response.status_code == 200

def test_save_roles(client):
    """Тест сохранения ролей."""
    headers = {'Authorization': 'Basic YWRtaW46c2VjdXJlX3Bhc3N3b3Jk'}
    
    role_data = {
        'roles[0][role_name]': 'test_role',
        'roles[0][display_name]': 'Test Role',
        'roles[0][telegram_bot_name]': 'Test_Role_Bot',
        'roles[0][system_prompt_file]': 'roles/prompts/test.md',
        'roles[0][agent_type]': 'gemini_acp',
        'roles[0][cli_command]': 'gemini --experimental-acp'
    }
    
    response = client.post('/save', data=role_data, headers=headers)
    assert response.status_code == 200
```

### Интеграционные тесты

```python
@pytest.mark.asyncio
async def test_reload_flag_creation():
    """Тест создания .reload флага."""
    # Сохранение через веб-интерфейс
    # Проверка создания .reload файла
    # Проверка перезагрузки конфигурации
    pass
```

### Тестирование безопасности

```python
def test_csrf_protection(client):
    """Тест CSRF защиты."""
    headers = {'Authorization': 'Basic YWRtaW46c2VjdXJlX3Bhc3N3b3Jk'}
    
    # Запрос без CSRF токена
    response = client.post('/save', data={}, headers=headers)
    assert response.status_code == 403

def test_sql_injection_protection(client):
    """Тест защиты от SQL-инъекций."""
    malicious_input = "'; DROP TABLE roles; --"
    # Проверка обработки вредоносного ввода
    pass
```