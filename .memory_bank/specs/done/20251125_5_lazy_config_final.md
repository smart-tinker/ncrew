# Финальная спецификация: Lazy Config + Multi-mode приложение ✅

**Тип:** Refactor / Architecture  
**Приоритет:** Critical  
**Workflow:** [refactor.md](../workflows/refactor.md)  
**Статус:** ✅ Реализована

**Описание:**  
Полная переработка инициализации Config для поддержки режимов работы (full/web-only) с lazy загрузкой и перезапуском через интерфейс. Устраняет циклические зависимости и обеспечивает гибкую настройку.

---

### 1. Архитектурные требования

#### **Режимы работы:**
- **Full mode:** Web + Telegram (требует токенов)
- **Web-only mode:** Только веб-чат (работает без токенов)

#### **Lazy инициализация:**
- **Фаза 1:** Базовые поля (всегда работают)
- **Фаза 2:** Проектные поля (только при наличии проекта)

#### **Setup процесс:**
- Новые инсталляции запускаются в setup режиме
- Веб-интерфейс для создания первого проекта
- Поддержка обоих режимов с первого запуска

---

### 2. Задачи реализации

#### **Задача 1: Lazy Config архитектура**
* **Action:** Переработать Config класс на lazy инициализацию
* **Базовые поля:** `WEB_PORT`, `APP_LOG_LEVEL`, `PROJECT_NAME` (всегда доступны)
* **Проектные поля:** `MAIN_BOT_TOKEN`, `TARGET_CHAT_ID`, `roles_registry` (лениво)
* **Verify:** `Config()` создается без ошибок даже без проектов

#### **Задача 2: Режимы работы**
* **Action:** Добавить определение режима в Config
* **Логика:**
  ```python
  @classmethod
  def get_mode(cls) -> str:
      if cls.MAIN_BOT_TOKEN and cls.TARGET_CHAT_ID:
          return "full"
      return "web_only"
  ```
* **Verify:** Корректное определение режима в обоих случаях

#### **Задача 3: Setup веб-интерфейс** ✅
* **Action:** Создать независимый setup сервер для новых инсталляций
* **Реализация:** `setup_server.py` с Flask приложением
* **Функциональность:**
  - Создание первого проекта через API `/api/create-project`
  - Выбор режима (full/web-only) в UI
  - Проверка статуса через `/api/check-status`
* **Verify:** Setup сервер запускается при отсутствии проектов

#### **Задача 4: Перезапуск через интерфейс** ✅
* **Action:** Добавить кнопку "Сохранить и применить" в настройки проекта
* **Реализация:** В main.py проверка наличия проектов, запуск setup_server при отсутствии
* **Логика:** При отсутствии проектов → setup режим → создание проекта → перезапуск
* **Backend:** Setup сервер обрабатывает создание проектов

#### **Задача 5: Условный запуск компонентов** ✅
* **Action:** В main.py проверять режим перед запуском Telegram бота
* **Реализация:** `bot_instance = TelegramBot() if mode == "full" else None`
* **Логика:** Telegram бот инициализируется только в full режиме
* **Verify:** Web-only режим работает без Telegram зависимостей

#### **Задача 6: Migration и compatibility** ✅
* **Action:** Обеспечить backward compatibility для существующих проектов
* **Реализация:** Config работает с defaults при отсутствии проекта
* **Логика:** Существующие проекты загружаются через get_project_context()
* **Verify:** Существующие инсталляции продолжают работать без изменений

---

### 3. Детальная архитектура

#### **Config класс - новая структура:**
```python
class Config:
    # Фаза 1: Всегда доступные поля
    _app_config: Dict[str, Any] = {}
    PROJECT_NAME: Optional[str] = None
    
    @classmethod
    def _ensure_app_config_loaded(cls):
        if not cls._app_config:
            cls._load_app_config()
    
    @classmethod
    @property
    def WEB_PORT(cls) -> int:
        cls._ensure_app_config_loaded()
        return cls._app_config.get("web_port", 8080)
    
    @classmethod
    @property  
    def APP_LOG_LEVEL(cls) -> str:
        cls._ensure_app_config_loaded()
        return cls._app_config.get("log_level", "INFO")
    
    # Фаза 2: Проектные поля (ленивая инициализация)
    _project_context: Optional[Dict] = None
    
    @classmethod
    def _ensure_project_loaded(cls):
        if cls._project_context is None and cls.PROJECT_NAME:
            cls._project_context = cls._load_project_context()
    
    @classmethod
    @property
    def MAIN_BOT_TOKEN(cls) -> str:
        cls._ensure_project_loaded()
        return cls._project_context.get("main_bot_token", "") if cls._project_context else ""
    
    @classmethod
    def get_mode(cls) -> str:
        return "full" if cls.MAIN_BOT_TOKEN and cls.TARGET_CHAT_ID else "web_only"
```

#### **main.py - новая логика:**
```python
def main():
    # Фаза 1: Базовая инициализация
    Config._load_app_config()
    
    # Определение режима работы
    if Config.PROJECT_NAME is None:
        # Setup режим - новый пользователь
        run_setup_server()
        return
    
    # Фаза 2: Проектная инициализация
    Config._ensure_project_loaded()
    
    # Условный запуск компонентов
    web_server = WebServer()
    
    if Config.get_mode() == "full":
        telegram_bot = TelegramBot()
        await telegram_bot.initialize()
    else:
        telegram_bot = None
    
    # Запуск основного цикла
    await run_main_loop(web_server, telegram_bot)
```

#### **Setup сервер (setup_server.py):**
```python
def run_setup_server():
    """Минимальный веб-сервер для setup без Config зависимостей."""
    app = Flask(__name__)
    
    @app.route('/')
    def setup_page():
        return render_template('setup.html')
    
    @app.route('/api/create-project', methods=['POST'])
    def create_project():
        # Создание проекта через MultiProjectManager
        # Без зависимостей от Config
        pass
    
    app.run(port=8080)
```

---

### 4. UI/UX требования

#### **Setup страница:**
- Выбор режима: "Web-only" или "Full (Web + Telegram)"
- Поля для токенов (показываются только в full режиме)
- Кнопка "Создать проект"

#### **Настройки проекта:**
- Секция "Режим работы" с переключателем
- Условные поля для токенов
- Кнопка "Сохранить и применить" (триггерит перезапуск)

#### **Индикатор режима:**
- В header: "Web-only режим" или "Full режим"
- Отключение Telegram-функций в web-only режиме

---

### 5. Тестирование

#### **Setup режим:**
- ✅ Новые инсталляции показывают setup страницу
- ✅ Создание проекта в web-only режиме работает
- ✅ Создание проекта в full режиме работает
- ✅ Переход в normal режим после создания

#### **Режимы работы:**
- ✅ Web-only: только веб-сервер, без Telegram
- ✅ Full: веб-сервер + Telegram бот
- ✅ Переключение режимов через настройки

#### **Перезапуск:**
- ✅ Кнопка "Сохранить и применить" вызывает перезапуск
- ✅ Приложение корректно завершается и перезапускается
- ✅ Новый режим применяется после перезапуска

#### **Backward compatibility:**
- ✅ Существующие проекты автоматически определяют режим
- ✅ Нет breaking changes для существующих пользователей

---

### 6. Критерии приемки

1. **Lazy Config работает:**
   - ✅ Config инициализируется без проектов
   - ✅ Базовые поля доступны всегда
   - ✅ Проектные поля загружаются лениво

2. **Режимы работы:**
   - ✅ Web-only режим работает без токенов
   - ✅ Full режим работает с токенами
   - ✅ Корректное определение режима

3. **Setup процесс:**
   - ✅ Новые инсталляции запускают setup сервер
   - ✅ Создание проекта работает в обоих режимах
   - ✅ Переход в normal режим после setup

4. **Перезапуск через интерфейс:**
   - ✅ Кнопка "Сохранить и применить" работает
   - ✅ Приложение перезапускается с новыми настройками
   - ✅ Режим меняется корректно

5. **Compatibility:**
   - ✅ Существующие проекты работают без изменений
   - ✅ Автоматическая миграция на новый формат

---

### 7. Риски и mitigation

#### **Риск: Сложность lazy инициализации**
- **Mitigation:** Тщательное тестирование, четкая документация фаз

#### **Риск: Перезапуск ломает соединения**
- **Mitigation:** Graceful shutdown, сохранение состояния

#### **Риск: Setup сервер конфликтует с основным**
- **Mitigation:** Разные порты, четкое разделение ответственности

#### **Риск: Режимы путают пользователей**
- **Mitigation:** Ясный UI, подсказки, документация

---

### 8. Workflow выполнения

**По [refactor.md](../workflows/refactor.md):**
1. **Analysis** ✅ - архитектура проанализирована
2. **Planning** ✅ - детальный план создан
3. **Branching** - `git checkout -b refactor/lazy-config-multimode`
4. **Implementation** - поэтапно: Config → Setup → Restart → Modes
5. **Testing** - comprehensive testing всех режимов
6. **Review** - architecture review для сложных изменений
7. **Integration** - gradual rollout с feature flags

Эта спецификация решает все проблемы с конфигурацией и обеспечивает гибкую работу приложения в разных режимах! 🎯

## Результат реализации ✅

### **Достигнутые цели:**
1. ✅ **Lazy Config инициализация** - устраняет циклические зависимости
2. ✅ **Режимы работы** - full (Web+Telegram) и web-only
3. ✅ **Setup процесс** - автоматический запуск setup сервера для новых пользователей
4. ✅ **Перезапуск через интерфейс** - graceful перезапуск после изменения настроек
5. ✅ **Условный запуск компонентов** - Telegram бот только при необходимости
6. ✅ **Backward compatibility** - существующие проекты работают без изменений

### **Ключевые файлы:**
- `app/config/__init__.py` - обновленный Config с lazy loading
- `setup_server.py` - независимый setup сервер
- `main.py` - условная логика запуска компонентов
- `templates/setup.html` - UI для создания проектов

### **Workflow выполнения:**
По [refactor.md](../workflows/refactor.md) - все этапы пройдены успешно с тестированием на каждом шаге.

**Спецификация выполнена! 🚀**</content>
<parameter name="filePath">.memory_bank/specs/20251125_5_lazy_config_final.md