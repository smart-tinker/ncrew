# Руководство по репозиторию

## Структура проекта и модули
- Точка входа — `main.py`; общие настройки собраны в `config.py`, а маршрутизация ролей реализована в `ncrew.py`.
- Папка `connectors/` содержит ACP-модули (`opencode_acp_connector.py`, `qwen_acp_connector.py`, `gemini_acp_connector.py`) и headless CLI-модули (`codex_cli_connector.py`, `claude_cli_connector.py`) поверх `base.py`.
- Telegram-логика изолирована в `telegram_bot.py`, веб-UI для ролей — в `web_server.py` + `templates/index.html`, вспомогательные утилиты лежат в `utils/`, файловое хранилище реализовано в `storage/file_storage.py`. Рабочие данные (`data/conversations`, `data/logs`) не коммитим.
- Тесты повторяют структуру исходников внутри `tests/`; создавая новый модуль, добавляем соседний `tests/<module>_test.py`.

## Сборка, запуск и тесты
- `pip install -r requirements.txt` — установка зависимостей под Python 3.10+.
- `python main.py` — запуск бота с конфигурацией из `.env` и `roles/agents.yaml`; для детальной отладки добавляем `LOG_LEVEL=DEBUG`.
- `python web_server.py` — запуск панели для редактирования ролей/токенов (Basic Auth через `WEB_ADMIN_USER/PASS`).
- `pytest` — полный тест-ран; для точечных проверок есть `tests/test_opencode_acp.py`, `tests/test_codex_cli_connector.py`, `tests/test_web_server.py` и т.д.

## Стиль кода и именование
- Соблюдаем стандартный Python-стиль: 4 пробела, snake_case для функций/переменных, PascalCase для классов, UPPER_SNAKE_CASE для констант.
- Асинхронные функции не блокируют event loop: ввод/вывод и запуск CLI выносим в обёртки `BaseConnector`.
- Логи настраиваем через `utils.logger.setup_logger`; эмодзи и форматирование придерживаются паттернов из `main.py`.
- Новые публичные функции и методы по возможности аннотируем типами и сопровождаем комментариями только там, где логика неочевидна.

## Рекомендации по тестированию
- Используем pytest и `pytest-asyncio`; асинхронные тесты помечаем `@pytest.mark.asyncio`.
- Имена тестов описательные (`test_connector_handles_timeout`), в проверках учитываем как успешные, так и аварийные сценарии, включая запись в `data/conversations`.

## Коммиты и pull request’ы
- Сообщения коммитов — короткие, в повелительном наклонении и до 72 символов (`Add OpenAI SDK connector`, `Fix context handling for user questions`).
- В PR описываем суть изменений, перечисляем проверки (`pytest`, ручной/веб-прогон), связываем задачу с issue; логи прикладываем только без токенов.

## Безопасность и конфигурация
- Никогда не коммитим `.env`, реальные токены или журналы переписок; для примеров используем `.env.example`.
- При изменении ролей синхронно обновляем `roles/agents.yaml`, соответствующие `roles/prompts/*` и при необходимости форму `templates/index.html`.
- Все CLI-агенты (OpenCode, Qwen, Gemini, Codex, Claude) аутентифицируются локально. Проходим `login/setup-token` вручную в том же окружении, где крутится NeuroCrew; никаких API-ключей в `.env` не храним.
