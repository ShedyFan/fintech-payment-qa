# BUG-04 — Валидный JSON с неверной схемой в localStorage роняет экран истории

- **Серьёзность:** высокая
- **Область:** хранение
- **Сценарий тест-плана:** APP-014
- **Найдено:** независимым аудитом (`sessions/2026-08-28-independent-audit.md`,
  AUDIT-06), подтверждено браузерным прогоном 2026-08-28.

## Шаги воспроизведения

1. Открыть `http://localhost:8765/app/index.html`.
2. В DevTools → Application → Local Storage записать в ключ
   `payments-cabinet-v1` строку: `{"balance":0,"operations":[{}]}`
   (валидный JSON, но элемент `operations` без полей `amount`/`fee`/…).
3. Перезагрузить страницу.

## Ожидаемый результат

`SPEC.md` → «Состояния → Повреждённое хранилище»: «при нечитаемом `localStorage`
состояние сбрасывается к начальному, ошибка в консоль не выбрасывается». То есть
экран должен показать начальное состояние (баланс 50 000.00, «Операций пока
нет») без ошибок.

## Фактический результат

`loadState()` проверяет только `typeof parsed.balance === "number"` и
`Array.isArray(parsed.operations)` — форму элементов массива не проверяет.
`{"balance":0,"operations":[{}]}` проходит валидацию. Далее `renderHistory()`
вызывает `op.amount.toFixed(2)` на `undefined`.

Консоль после перезагрузки (браузерный прогон):

```
TypeError: Cannot read properties of undefined (reading 'toFixed')
    at renderHistory (http://localhost:8765/app/index.html:416:40)
    at render (…:437:5)
```

Ошибка повторяется каждую секунду — `setInterval(renderHistory, 1000)` вызывает
`renderHistory` снова. Таблица истории не строится.

## Доказательство

Вывод `read_console_messages` (onlyErrors) сразу после загрузки страницы с
подставленным значением — 5 одинаковых `TypeError` в `renderHistory`
(строка 416, `op.amount.toFixed`).

Код `app/index.html`:

```js
function loadState() {
  // ...
  if (!parsed || typeof parsed.balance !== "number" || !Array.isArray(parsed.operations)) {
    return defaultState();
  }
  return parsed;               // элементы operations не валидируются
}
// renderHistory():
'<td class="num">' + op.amount.toFixed(2) + "</td>"   // op.amount === undefined -> throw
```

APP-012 покрывает только синтаксически битый JSON (`{битый`) — там
`JSON.parse` бросает и `catch` возвращает `defaultState()`. Случай
«валидный JSON, неверная схема» не покрыт.

## Предлагаемое направление фикса

В `loadState()` проверять форму каждого элемента `operations` (наличие и типы
`amount`, `fee`, `status`, `recipient`, `createdAt`, `day`); при несоответствии —
`defaultState()`. Отдельная сессия «фикс», как для BUG-01.
