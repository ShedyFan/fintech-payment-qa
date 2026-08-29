// Playwright-сценарий для app/index.html.
// Запуск: npm test  (или см. tests/README.md).
//
// На текущей версии app/ все 9 тестов ЗЕЛЁНЫЕ (прогон 2026-08-29,
// sessions/2026-08-29-fix-bug-02-03-04.md).
//   APP-001/005/007 — базовое поведение;
//   APP-003 — регрессия по фикс-сессии BUG-01 (был красным до 2026-08-28);
//   APP-008 — регрессия по фикс-сессии BUG-02: дневной лимит по местной дате,
//             граница «ровно лимит» / «сверх лимита» через seed-состояние;
//   APP-009 — регрессия по фикс-сессии BUG-03 (был красным до 2026-08-29):
//             "1 000" отклоняется, а не усекается до 1;
//   APP-011 — окно отмены 60 сек: у операции старше окна кнопки «Отменить» нет
//             (seed с createdAt в прошлом — без ожидания реальных 60 сек);
//   APP-012 — персистентность + восстановление после синтаксически битого JSON,
//             консоль чистая;
//   APP-014 — регрессия по фикс-сессии BUG-04 (был красным до 2026-08-29):
//             валидный JSON с неверной схемой не роняет экран истории.

const { test, expect } = require('@playwright/test');

const URL = 'http://localhost:8765/app/index.html';

async function reset(page) {
  await page.goto(URL);
  await page.click('#reset');
}

async function transfer(page, recipient, amount) {
  await page.fill('#recipient', recipient);
  await page.fill('#amount', String(amount));
  await page.click('#send');
}

// Подставить состояние в localStorage и перезагрузить (seed для граничных
// сценариев). Если у операции day === 'TODAY', подставляется локальный ключ
// суток — так же, как его строит todayKey() в app/ (по времени браузера).
async function seedAndReload(page, state) {
  await page.goto(URL);
  await page.evaluate((s) => {
    const d = new Date();
    const today = d.getFullYear() + '-' +
      ('0' + (d.getMonth() + 1)).slice(-2) + '-' +
      ('0' + d.getDate()).slice(-2);
    (s.operations || []).forEach((op) => { if (op.day === 'TODAY') op.day = today; });
    localStorage.setItem('payments-cabinet-v1', JSON.stringify(s));
  }, state);
  await page.reload();
}

// null-safe: после reset() ключ localStorage удалён, отклонённый перевод в него
// ничего не пишет — тогда возвращаем состояние по умолчанию.
function storedState(page) {
  return page.evaluate(() => {
    const raw = localStorage.getItem('payments-cabinet-v1');
    return raw ? JSON.parse(raw) : { balance: 50000, operations: [] };
  });
}

test.beforeEach(async ({ page }) => {
  await reset(page);
});

// --- ЗЕЛЁНЫЕ: базовое поведение ---

test('APP-001 перевод 1000 — баланс и история', async ({ page }) => {
  await transfer(page, 'ООО Ромашка', 1000);
  await expect(page.locator('#balance')).toHaveText('48990.00 ₽');
  await expect(page.locator('#history tbody tr')).toHaveCount(1);
});

test('APP-005 нулевая сумма отклонена', async ({ page }) => {
  await transfer(page, 'T', 0);
  await expect(page.locator('#msg')).toHaveText('Сумма должна быть больше нуля.');
  const st = await storedState(page);
  expect(st.operations).toHaveLength(0);
});

test('APP-007 нехватка средств с учётом комиссии', async ({ page }) => {
  await transfer(page, 'T', 49995); // 49995 + комиссия 300 > 50000
  await expect(page.locator('#msg')).toHaveText('Недостаточно средств с учётом комиссии.');
});

// --- ЗЕЛЁНЫЙ: регрессия по фиксу BUG-01 ---

test('APP-003 [BUG-01 fixed] комиссия округляется, баланс без долей копейки', async ({ page }) => {
  await transfer(page, 'Раунд Тест', 1234.56);
  const st = await storedState(page);
  expect(st.operations[0].fee).toBe(12.35);           // 12.3456 -> HALF_UP -> 12.35
  expect(st.balance).toBe(Number(st.balance.toFixed(2)));
  await expect(page.locator('#balance')).toHaveText('48753.09 ₽');
});

// --- КРАСНЫЕ: падают на открытых дефектах ---

test('APP-009 [BUG-03] разделитель разрядов в сумме', async ({ page }) => {
  await transfer(page, 'T', '1 000'); // пользователь имеет в виду 1000
  const st = await storedState(page);
  if (st.operations.length) {
    expect(st.operations[0].amount).toBe(1000); // а не 1
  } else {
    await expect(page.locator('#msg')).not.toHaveText(''); // либо явный отказ
  }
});

test('APP-014 [BUG-04] валидный JSON с неверной схемой не роняет экран', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(URL);
  await page.evaluate(() =>
    localStorage.setItem('payments-cabinet-v1', '{"balance":0,"operations":[{}]}'));
  await page.reload();
  await page.waitForTimeout(1500); // пережить один тик setInterval(renderHistory, 1000)
  await expect(page.locator('#history .empty')).toBeVisible();
  await expect(page.locator('#balance')).toHaveText('50000.00 ₽');
  expect(errors, 'в консоли не должно быть ошибок').toEqual([]);
});

// --- ЗЕЛЁНЫЕ: граничные сценарии через seed-состояние (2026-08-29) ---

test('APP-008 [BUG-02] дневной лимит: граница «ровно лимит» / «сверх лимита»', async ({ page }) => {
  // Расход дня уже 99 900 (две операции done за сегодня по местной дате).
  await seedAndReload(page, {
    balance: 5000,
    operations: [
      { id: 'seed-a', recipient: 'seed', amount: 60000, fee: 0, status: 'done', createdAt: Date.now() - 3600000, day: 'TODAY' },
      { id: 'seed-b', recipient: 'seed', amount: 39900, fee: 0, status: 'done', createdAt: Date.now() - 3600000, day: 'TODAY' },
    ],
  });
  // Перевод 100 -> расход ровно 100 000, граница разрешена.
  await transfer(page, 'T', 100);
  await expect(page.locator('#msg')).toBeEmpty();
  let st = await storedState(page);
  expect(st.operations.filter((o) => o.status === 'done')).toHaveLength(3);
  // Ещё 200 -> уже сверх лимита, отказ, баланс не тронут.
  const balBefore = st.balance;
  await transfer(page, 'T', 200);
  await expect(page.locator('#msg')).toHaveText('Превышен дневной лимит переводов.');
  st = await storedState(page);
  expect(st.balance).toBe(balBefore);
});

test('APP-011 окно отмены 60 сек: у операции старше окна кнопки «Отменить» нет', async ({ page }) => {
  await seedAndReload(page, {
    balance: 48990,
    operations: [
      { id: 'old-1', recipient: 'T', amount: 1000, fee: 10, status: 'done', createdAt: Date.now() - 61000, day: 'TODAY' },
    ],
  });
  await page.waitForTimeout(1200); // тик renderHistory
  await expect(page.locator('#history tbody tr')).toHaveCount(1);
  await expect(page.locator('#history [data-cancel]')).toHaveCount(0);
  // контроль: свежая операция кнопку показывает
  await transfer(page, 'Fresh', 500);
  await expect(page.locator('#history [data-cancel]')).toHaveCount(1);
});

test('APP-012 персистентность + восстановление после битого JSON, консоль чистая', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await reset(page);
  await transfer(page, 'A', 1000);
  await transfer(page, 'B', 2000);
  await page.reload();
  await expect(page.locator('#history tbody tr')).toHaveCount(2); // персистентность
  await page.evaluate(() => localStorage.setItem('payments-cabinet-v1', '{ broken json'));
  await page.reload();
  await page.waitForTimeout(1500);
  await expect(page.locator('#history .empty')).toBeVisible();
  await expect(page.locator('#balance')).toHaveText('50000.00 ₽');
  expect(errors, 'в консоли не должно быть ошибок').toEqual([]);
});
