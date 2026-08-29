// Медленный сценарий — реальное ожидание окна отмены 60 секунд.
// Вынесен из payments.spec.js, чтобы `npm test` оставался быстрым.
// Запуск: npm run test:slow  (нужен поднятый http.server 8765).
//
// payments.spec.js уже проверяет APP-011 через seed (createdAt в прошлом) —
// быстро и детерминированно. Этот файл проверяет то же поведение вживую:
// сделать перевод, реально подождать > 60 секунд, убедиться, что кнопка
// «Отменить» исчезла по таймеру setInterval(renderHistory, 1000).

const { test, expect } = require('@playwright/test');

const URL = 'http://localhost:8765/app/index.html';

test('APP-011 (live) кнопка «Отменить» исчезает после реальных 60+ секунд', async ({ page }) => {
  test.setTimeout(120000);

  await page.goto(URL);
  await page.click('#reset');
  await page.fill('#recipient', 'Live Timer');
  await page.fill('#amount', '1000');
  await page.click('#send');

  // сразу после перевода кнопка есть
  await expect(page.locator('#history [data-cancel]')).toHaveCount(1);

  // на 30-й секунде окно ещё открыто (таймер реально идёт, а не «никогда не было»)
  await page.waitForTimeout(30000);
  await expect(page.locator('#history [data-cancel]')).toHaveCount(1);

  // после 63 секунд окно закрыто — renderHistory по setInterval убрал кнопку
  await page.waitForTimeout(33000);
  await expect(page.locator('#history [data-cancel]')).toHaveCount(0);

  // операция на месте, статус «Исполнен», баланс не изменился обратно
  await expect(page.locator('#history tbody tr')).toHaveCount(1);
  await expect(page.locator('#history .status-done')).toBeVisible();
  await expect(page.locator('#balance')).toHaveText('48990.00 ₽');
});
