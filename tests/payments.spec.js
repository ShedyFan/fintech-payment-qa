// Playwright-сценарий для app/index.html.
// Запуск: npm test  (или см. tests/README.md).
//
// На текущей версии app/ все 6 тестов ЗЕЛЁНЫЕ (прогон 2026-08-29,
// sessions/2026-08-29-fix-bug-02-03-04.md).
//   APP-001/005/007 — базовое поведение;
//   APP-003 — регрессия по фикс-сессии BUG-01 (был красным до 2026-08-28);
//   APP-009 — регрессия по фикс-сессии BUG-03 (был красным до 2026-08-29):
//             "1 000" отклоняется, а не усекается до 1;
//   APP-014 — регрессия по фикс-сессии BUG-04 (был красным до 2026-08-29):
//             валидный JSON с неверной схемой не роняет экран истории.
// BUG-02 (часовой пояс дневного лимита) тоже исправлен в коде 2026-08-29,
// но отдельного автотеста на границу суток здесь нет — нужен контроль
// системного времени; проверяется ручным прогоном с seed-состоянием.

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
