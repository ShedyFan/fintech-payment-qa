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

## Исправлено

- **Сессия:** `sessions/2026-08-29-fix-bug-02-03-04.md`.
- **Архитектурное решение:** полная отбраковка состояния целиком при первой же
  невалидной записи, **не** построчная фильтрация. `balance` в этом продукте
  хранится отдельно и не пересчитывается из `operations` — частичная фильтрация
  дала бы ложное чувство целостности денежного следа и ослабила бы `spentToday()`
  как бизнес-инвариант; `SPEC.md` описывает контракт как двоичный сброс.
  Поле `id` включено в обязательную схему (используется в `cancelOperation`).

Изменения в `app/index.html`:

```js
// новая функция
function isValidOperation(op) {
  return op !== null && typeof op === "object" &&
    typeof op.id === "string" && typeof op.recipient === "string" &&
    typeof op.amount === "number" && isFinite(op.amount) &&
    typeof op.fee === "number" && isFinite(op.fee) &&
    (op.status === "done" || op.status === "cancelled") &&
    typeof op.createdAt === "number" && isFinite(op.createdAt) &&
    typeof op.day === "string";
}

// loadState(): плюс isFinite(parsed.balance) и цикл по operations —
// один невалидный элемент => return defaultState().
// renderHistory(): барьер вторым слоем — if (!isValidOperation(op)) continue;
// (и такой же guard в цикле поиска lastDoneIndex).
```

Заодно закрыт смежный дефект того же класса: `typeof NaN === "number"` проходил
исходную проверку баланса — добавлена `isFinite(parsed.balance)`.

**Проверка:** `tests/payments.spec.js` → `APP-014 [BUG-04]` теперь **PASS**
(`{"balance":0,"operations":[{}]}` → экран показывает начальное состояние,
`#history .empty` виден, баланс `50000.00 ₽`, `pageerror` пуст). Добавлен и
`APP-012` (синтаксически битый JSON `{ broken json` → тот же сброс). Полный
прогон 9/9 PASS — `sessions/2026-08-29-fix-bug-02-03-04.md`.
