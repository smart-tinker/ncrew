# Глобальная очистка архитектуры (Delete-driven Refactoring)

**Тип:** Refactor
**Приоритет:** Critical
**Workflow:** [refactor.md](../workflows/refactor.md)

**Описание:**
Удаление неиспользуемого слоя абстракций ("Interface Agnostic Application"), который дублирует функционал и усложняет поддержку. Возврат к чистой архитектуре MVP, используемой в `main.py`.

---

### 1. REQs (Требования)
1.  Удалить код, не участвующий в цепочке вызовов `main.py -> TelegramBot -> NeuroCrewLab -> Connectors`.
2.  Очистить ядро (`engine.py`) от методов, поддерживающих удаляемый код.
3.  Удалить тесты, проверяющие мертвый код.
4.  Гарантировать, что `main.py` и базовые сценарии продолжают работать.

### 2. Plan & Test Strategy

#### Шаг 1: Удаление "Мертвого слоя" (Application Wrapper)
*   **Test Fail / Baseline:** Запустить `pytest tests/test_mvp_critical.py` (должен проходить). Запустить `pytest tests/test_implementation_integration.py` (этот тест мы будем удалять, так как он тестирует мертвый код).
*   **Action:** Удалить:
    - `app/application.py`
    - `app/interfaces/interface_manager.py`
    - `app/interfaces/base.py` (и связанные `__init__.py`)
    - `app/interfaces/telegram/adapter.py`
    - `app/interfaces/web/adapter.py`
*   **Test Pass:** Убедиться, что статический анализ не показывает ошибок импорта в оставшихся файлах.

#### Шаг 2: Очистка Ядра (`app/core/engine.py`)
*   **Test Fail / Baseline:** Проверить, что `main.py` работает.
*   **Action:** Удалить из `NeuroCrewLab`:
    - Свойства `connector_sessions`, `chat_role_pointers` (если они дублируются), `role_last_seen_index` (легаси геттеры).
    - Метод `_reset_chat_role_sessions`.
    - Методы-обертки, помеченные как LEGACY.
*   **Verify:** Код `main.py` не должен ссылаться на удаленные атрибуты.

#### Шаг 3: Реструктуризация и Чистка Тестов
*   **Test Fail:** Запустить полный `pytest`. Ожидается падение тестов, импортирующих `app.application` или `app.interfaces.base`.
*   **Action:**
    - Удалить `tests/test_implementation_integration.py`.
    - Удалить `tests/test_mvp_validation.py`.
    - Обновить `tests/test_mvp_critical.py`: убрать использование `MockNeuroCrewApplication` и `MockInterfaceManager`. Переписать на проверку прямого взаимодействия с `NeuroCrewLab` и `TelegramBot`.
    - Переименовать `tests/test_mvp_critical.py` в `tests/test_flow_integration.py`.
*   **Test Pass:** `pytest` должен проходить 100% (зеленый).

#### Шаг 4: Упрощение файловой структуры
*   **Action:**
    - Переместить `app/interfaces/telegram/bot.py` -> `app/interfaces/telegram_bot.py`.
    - Обновить импорты в `main.py`.
    - Удалить пустую папку `app/interfaces/telegram/`.

---

### Критерии приемки (Definition of Done)
1.  Файлы `application.py`, `interface_manager.py` отсутствуют.
2.  `main.py` запускается без ошибок.
3.  Команда `pytest` выполняется успешно (все тесты зеленые).
4.  В коде нет импортов `app.application` или `app.interfaces.base`.