### **Техническая Спецификация: Модуль Коннекторов для Agentic CLI**

**1. Общая Цель**

Создать набор Python-классов (Коннекторов), каждый из которых обеспечивает надежное, stateful (с сохранением состояния) взаимодействие с одним из целевых Agentic CLI. Все коннеторы должны реализовывать единый интерфейс, но их внутренняя механика будет адаптирована под особенности каждого CLI.

**2. Ключевой Архитектурный Принцип: Stateful-сессии через `subprocess.Popen`**

В отличие от простого вызова `subprocess.run()`, который запускает и завершает процесс на каждый запрос, мы будем использовать `asyncio.create_subprocess_exec` (аналог `subprocess.Popen`) для запуска **долгоживущего** процесса для каждой CLI-сессии.

**Жизненный цикл сессии:**
1.  **Запуск (`launch`):** При первом обращении к роли, Оркестратор создает экземпляр нужного коннектора и вызывает его метод `launch()`. Коннектор запускает CLI-процесс с флагами интерактивного режима. Сразу после запуска он отправляет в `stdin` процесса **системный промпт**.
2.  **Взаимодействие (`execute`):** При каждом последующем вызове, Оркестратор передает в метод `execute` коннектора новую "дельту" диалога. Коннектор форматирует ее и отправляет в `stdin` уже запущенного процесса. Затем он читает ответ из `stdout`.
3.  **Завершение (`shutdown`):** Когда сессия больше не нужна (например, при перезапуске `NeuroCrew Lab`), вызывается метод `shutdown()`, который корректно завершает дочерний CLI-процесс.

**3. Единый Интерфейс: `connectors/base.py`**

Все коннекторы должны наследовать от этого абстрактного класса. Это обеспечит унификацию на уровне Ядра (`ncrew.py`).

```python
# connectors/base.py

from abc import ABC, abstractmethod
import asyncio

class BaseConnector(ABC):
    """Абстрактный базовый класс для stateful-коннекторов к Agentic CLI."""

    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.logger = get_logger(f"{self.__class__.__name__}")

    @abstractmethod
    async def launch(self, command: str, system_prompt: str):
        """
        Запускает CLI-процесс в интерактивном режиме и отправляет системный промпт.
        Сохраняет процесс в self.process.
        """
        pass

    @abstractmethod
    async def execute(self, delta_prompt: str) -> str:
        """
        Отправляет новую часть диалога в запущенный процесс и возвращает ответ.
        """
        pass

    async def shutdown(self):
        """Корректно завершает CLI-процесс."""
        if self.process and self.process.returncode is None:
            self.logger.info(f"Завершение процесса {self.process.pid}...")
            self.process.terminate()
            await self.process.wait()
            self.logger.info("Процесс завершен.")

    def is_alive(self) -> bool:
        """Проверяет, активен ли CLI-процесс."""
        return self.process is not None and self.process.returncode is None
```

**4. Подробное Руководство по Реализации для Каждого Коннектора**

Ниже приведено детальное описание для разработчиков по каждому CLI.

---

#### **4.1. `QwenConnector` (для `QwenLM/qwen-code`)**

*   **Класс:** `connectors.qwen_connector.py -> class QwenConnector(BaseConnector)`
*   **Ключевая особенность:** Стандартный интерактивный скрипт на Python. Ожидает ввод, отдает вывод.
*   **Метод `launch(command: str, system_prompt: str)`:**
    1.  Разбить `command` на части: `command_parts = command.split()`.
    2.  Запустить процесс: `self.process = await asyncio.create_subprocess_exec(*command_parts, stdin=PIPE, stdout=PIPE, stderr=PIPE)`.
    3.  Сразу записать в `stdin` системный промпт. Важно добавить символ новой строки, чтобы CLI начал обработку: `self.process.stdin.write(f"{system_prompt}\n".encode())`.
    4.  *Не нужно* ждать ответа на системный промпт, считаем, что он просто устанавливает внутреннее состояние.
*   **Метод `execute(delta_prompt: str)`:**
    1.  Записать "дельту" в `stdin` процесса: `self.process.stdin.write(f"{delta_prompt}\n".encode())`.
    2.  **Чтение ответа:** Это самая сложная часть. Qwen CLI не имеет явного маркера конца ответа. Нужно читать `stdout` асинхронно до тех пор, пока не наступит короткий таймаут (например, 1-2 секунды) после получения последней строки.
        *   **Псевдокод чтения:**
            ```python
            response_lines = []
            while True:
                try:
                    # Читаем строку с таймаутом
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=2.0)
                    if not line: break # Процесс завершился
                    response_lines.append(line.decode().strip())
                except asyncio.TimeoutError:
                    # Если данных нет в течение 2 секунд, считаем, что агент закончил отвечать
                    break 
            return "\n".join(response_lines)
            ```*   **Парсинг ответа:** Qwen может "отзеркаливать" введенный промпт в своем ответе. Необходимо убирать из начала ответа строки, совпадающие с `delta_prompt`. Также убирать служебные строки вроде `Qwen:`.

---

#### **4.2. `GeminiConnector` (для `google-gemini/gemini-cli`)**

*   **Класс:** `connectors.gemini_connector.py -> class GeminiConnector(BaseConnector)`
*   **Ключевая особенность:** Более продвинутый инструмент, скорее всего имеет явный интерактивный режим.
*   **Метод `launch(command: str, system_prompt: str)`:**
    1.  Команда для запуска, вероятно, будет включать флаг `-i` или `--interactive`. Разработчику нужно будет проверить это (например, `gemini-cli -i --model gemini-pro`).
    2.  Разбить команду: `command_parts = command.split()`.
    3.  Запустить процесс: `self.process = await asyncio.create_subprocess_exec(...)`.
    4.  Gemini CLI может поддерживать системный промпт через специальную команду при запуске. Если это так, `system_prompt` нужно передать как часть `command`. Если нет — отправить его первым в `stdin`, как для Qwen.
*   **Метод `execute(delta_prompt: str)`:**
    1.  Записать "дельту" в `stdin`: `self.process.stdin.write(f"{delta_prompt}\n".encode())`.
    2.  **Чтение ответа:** `gemini-cli`, как и `qwen-code`, скорее всего не имеет четкого разделителя. Использовать ту же стратегию чтения с таймаутом, что и для Qwen.
*   **Парсинг ответа:** Gemini CLI может выводить дополнительную информацию (например, "Generating response..."). Эти строки нужно отфильтровать. Также убрать эхо промпта.

---

#### **4.3. `ClaudeConnector` (для `anthropics/claude-code`)**

*   **Класс:** `connectors.claude_connector.py -> class ClaudeConnector(BaseConnector)`
*   **Ключевая особенность:** Строгое форматирование диалога с ролями `Human:` и `Assistant:`.
*   **Метод `launch(command: str, system_prompt: str)`:**
    1.  Разбить команду: `command_parts = command.split()`.
    2.  Запустить процесс: `self.process = await asyncio.create_subprocess_exec(...)`.
    3.  Отправить системный промпт, отформатированный как первая реплика `Human`:
        ```python
        formatted_prompt = f"Human: {system_prompt}\n\nAssistant:"
        self.process.stdin.write(formatted_prompt.encode())
        ```
    4.  **Важно:** После отправки промпта нужно прочитать и проигнорировать первый ответ-подтверждение от Claude (например, "Ok, I understand my role."). Это "прогревает" сессию.
*   **Метод `execute(delta_prompt: str)`:**
    1.  Отформатировать "дельту" в виде реплики `Human`: `formatted_delta = f"\n\nHuman: {delta_prompt}\n\nAssistant:"`.
    2.  Записать в `stdin`: `self.process.stdin.write(formatted_delta.encode())`.
    3.  **Чтение ответа:** Claude обычно заканчивает свой ответ и ждет следующей реплики `Human:`. Поэтому здесь стратегия с таймаутом на чтение также является наиболее надежной.
*   **Парсинг ответа:** Из `stdout` нужно вырезать все, включая `Assistant:` и служебные фразы. Оставить только чистый текст ответа.

---

#### **4.4. `OpenCodeConnector` (для `sst/opencode`)**

*   **Класс:** `connectors.opencode_connector.py -> class OpenCodeConnector(BaseConnector)`
*   **Ключевая особенность:** Похож на `qwen-code`, это интерактивный инструмент, обертка над моделью.
*   **Метод `launch(command: str, system_prompt: str)`:**
    1.  Команда может потребовать флаг интерактивного режима, например `--interactive`.
    2.  Разбить команду, запустить процесс.
    3.  Отправить `system_prompt` с символом новой строки в `stdin`.
*   **Метод `execute(delta_prompt: str)`:**
    1.  Записать `delta_prompt` с символом новой строки в `stdin`.
    2.  Использовать стратегию чтения с таймаутом, как для Qwen.
*   **Парсинг ответа:** Убрать эхо промпта и любые статусные сообщения от CLI.

---

#### **4.5. `CodexConnector` (для `openai/codex`)**

*   **Класс:** `connectors.codex_connector.py -> class CodexConnector(BaseConnector)`
*   **Ключевая особенность:** Репозиторий является архивом. Скорее всего, разработчику придется использовать современный CLI-клиент для OpenAI API (например, из `pip install openai`). Спецификация будет для такого гипотетического клиента.
*   **Метод `launch(command: str, system_prompt: str)`:**
    1.  Команда для запуска, скорее всего, будет `openai api chat.completions.create ...` с флагом, позволяющим читать промпт из `stdin`.
    2.  Системный промпт для моделей OpenAI передается через специальную структуру (например, JSON). Коннектору нужно будет сформировать JSON-объект с `role: "system"` и `content: system_prompt` и передать его.
*   **Метод `execute(delta_prompt: str)`:**
    1.  Сформировать новый JSON-объект, добавляя сообщение с `role: "user"` и `content: delta_prompt` к истории.
    2.  Передать этот JSON в `stdin` процесса.
*   **Чтение и парсинг ответа:** CLI-клиенты OpenAI обычно возвращают чистый JSON в `stdout`. Ответ нужно будет распарсить и извлечь текст из `choices[0].message.content`. Здесь не нужен таймаут, можно просто прочитать `stdout` до конца (`await self.process.stdout.read()`).

---

**5. Общие Задачи и Ключевые Сложности для Разработчика**

1.  **Асинхронность:** Вся работа с `subprocess` должна быть реализована с использованием `asyncio.subprocess` для избежания блокировки основного потока приложения.
2.  **Определение Конца Ответа:** Это **главная техническая проблема**. Поскольку большинство CLI не предоставляют явного символа конца вывода (как `\0`), самой надежной стратегией является чтение `stdout` до тех пор, пока данные перестают поступать в течение заданного таймаута (1-2 секунды). Это нужно реализовать в виде надежной вспомогательной функции.
3.  **Обработка Ошибок:** Коннектор должен уметь обрабатывать:
    *   Падение CLI-процесса (`self.process.returncode != 0`).
    *   Ошибки, которые CLI пишет в `stderr`.
    *   Таймауты выполнения самой команды (если агент "завис").
4.  **Очистка Ресурсов:** Реализовать надежный метод `shutdown`, который гарантированно завершает дочерний процесс, чтобы избежать "зомби".
5.  **Логирование:** Каждый коннектор должен подробно логировать свои действия: запуск процесса, отправляемые данные (первые 200 символов), полученные ответы и любые ошибки.