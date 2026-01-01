# Playwright MCP: инструкция для агентов (opencode)

Этот документ — краткая памятка, как агенту управлять браузером через Playwright MCP, чтобы проверять UI (smoke/E2E), разбирать сценарии пользователя и собирать данные со страниц.

## Предусловия

1. Приложение запущено и доступно по URL (например: `http://127.0.0.1:3001/`).
   - Dev (Vite): `http://localhost:3000/` (proxy `/api` → backend)
   - Backend-only (после `vite build`): `http://localhost:3001/`
2. Если в окружении запрещены HTTP-запросы из shell (например, `curl` в sandbox), это не блокирует работу через Playwright: браузер ходит по сети сам.

## Базовый цикл (рекомендованный)

1. Открыть страницу: `mcp__playwright__browser_navigate`.
2. Получить дерево доступности (a11y snapshot) и `ref` элементов: `mcp__playwright__browser_snapshot`.
3. Клик/ввод/выбор опции через `ref`:
   - `mcp__playwright__browser_click`
   - `mcp__playwright__browser_type`
   - `mcp__playwright__browser_fill_form`
   - `mcp__playwright__browser_select_option`
4. Дождаться изменения UI: `mcp__playwright__browser_wait_for`.
5. Если появилось `alert/confirm/prompt`: `mcp__playwright__browser_handle_dialog`.

Важно: `ref` **не стабильны**. После навигации/перерендера/закрытия модалки делай новый `browser_snapshot`, иначе получишь ошибку “Ref not found”.

## Когда использовать `browser_run_code`

Инструмент `mcp__playwright__browser_run_code` полезен, когда:
- DOM часто меняется и `ref` “протухают”;
- нужно найти элемент по роли/тексту без ручного поиска `ref`;
- нужен “умный” локатор (например, “кнопка Run внутри карточки с заголовком X”).

Пример (паттерн “найти карточку по заголовку и нажать кнопку внутри”):

```js
async (page) => {
  const heading = page.getByRole('heading', { name: 'System Settings (~/.ncrew)' });
  const card = heading.locator('xpath=ancestor::*[.//button[normalize-space(.)=\"Run\"]][1]');
  await card.getByRole('button', { name: 'Run' }).click();
  return { url: page.url(), title: await page.title() };
}
```

## Минимальный набор инструментов

- Навигация: `mcp__playwright__browser_navigate`, `mcp__playwright__browser_navigate_back`
- Табы: `mcp__playwright__browser_tabs` (actions: `list`, `new`, `select`, `close`)
- “Посмотреть что на странице”: `mcp__playwright__browser_snapshot`
- Клик/ввод: `mcp__playwright__browser_click`, `mcp__playwright__browser_type`, `mcp__playwright__browser_fill_form`
- Ожидания: `mcp__playwright__browser_wait_for`
- Диалоги: `mcp__playwright__browser_handle_dialog`
- Отладка: `mcp__playwright__browser_console_messages`, `mcp__playwright__browser_network_requests`
- Скриншоты (для отчёта, не для действий): `mcp__playwright__browser_take_screenshot`
- Завершение: `mcp__playwright__browser_close`

## Пример “smoke”: проверить, что NCrew управляется через Playwright

1. Открыть главную:
   - `mcp__playwright__browser_navigate` → `http://localhost:3000/`
   - `mcp__playwright__browser_snapshot` → убедиться, что есть “Projects” и “+ Add Project”
2. Открыть форму добавления проекта:
   - `mcp__playwright__browser_click` по кнопке “+ Add Project”
   - `mcp__playwright__browser_fill_form` (Name/Path/Prefix)
   - `mcp__playwright__browser_click` по “Cancel” (чтобы ничего не менять)
3. Перейти на страницу проекта:
   - `mcp__playwright__browser_click` по ссылке проекта
   - `mcp__playwright__browser_snapshot` → увидеть “Tasks (…)”
4. Открыть/закрыть модалки:
   - `mcp__playwright__browser_click` по “Edit” → “Cancel”
   - `mcp__playwright__browser_click` по “Run” у задачи → “Cancel”
5. Проверить диалог:
   - `mcp__playwright__browser_click` по “Refresh Models”
   - `mcp__playwright__browser_handle_dialog` (accept=true)

## Типовые проблемы и быстрые решения

- **“Ref not found”**: снят старый snapshot → повтори `mcp__playwright__browser_snapshot`, возьми актуальный `ref`.
- **Нажатие не срабатывает**: элемент перекрыт модалкой/оверлеем → закрой модалку или кликай внутри неё; при необходимости используй `browser_run_code`.
- **Нужно подождать рендер/данные**: `mcp__playwright__browser_wait_for` по тексту (или `time`), затем новый snapshot.
