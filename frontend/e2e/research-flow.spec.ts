import { expect, test } from '@playwright/test';

const number = /-?\d+\.\d+/;

test('terminal: search, select, inspect metrics, jump to Curve Lab', async ({ page }) => {
  await page.goto('/terminal');
  const search = page.getByLabel('Search securities');
  await expect(search).toBeVisible();
  await page.keyboard.press('/');
  await expect(search).toBeFocused();
  await page.keyboard.type('Harborview');
  const first = page.locator('.result-list button').first();
  await expect(first).toContainText('Harborview');
  await first.click();
  await expect(page).toHaveURL(/\/terminal\/security\/BM-C-/);

  const metric = (label: string) => page.locator('.metric', { hasText: label }).locator('b');
  await expect(metric('Clean (mid)')).toHaveText(number);
  await expect(metric('DV01')).toHaveText(/^-0\.\d+/); // signed: price falls when rates rise
  await expect(metric('Bid / Ask')).toHaveText(/\d+\.\d+ \/ \d+\.\d+/);
  await expect(page.getByText('Remaining cash flows')).toBeVisible();

  await page.getByRole('link', { name: /Shock the curve/ }).click();
  await expect(page).toHaveURL(/curve-lab\?security=BM-C-/);
});

test('terminal: search with no matches shows an empty state', async ({ page }) => {
  await page.goto('/terminal');
  await page.getByLabel('Search securities').fill('zzzz-no-such-bond');
  await expect(page.getByText('No securities match')).toBeVisible();
});

test('curve lab: overlay, shock, reprice, reset', async ({ page }) => {
  await page.goto('/curve-lab?security=BM-T-0005&dates=2026-11-06,2024-11-06');
  // 1.5M bill did not exist in Nov 2024: shown as n/a, not zero
  const row = page.locator('table.data tbody tr', { hasText: /^\s*1\.5M/ });
  await expect(row.locator('td').nth(2)).toHaveText('n/a');

  await page.getByRole('button', { name: '+50', exact: true }).click();
  await expect(page.getByText('Scenario modified (unsaved)')).toBeVisible();
  const valuation = page.locator('.lab-valuation');
  await expect(valuation.getByText('updating…')).toBeHidden();
  const change = valuation.locator('tr', { hasText: 'Change %' }).locator('td').last();
  await expect(change).toHaveText(/^−\d+\.\d+%$/);
  await expect(page).toHaveURL(/shock=p50/);

  await page.getByRole('button', { name: 'Reset scenario' }).click();
  await expect(page.getByText('Scenario modified (unsaved)')).toBeHidden();
});

test('curve lab: out-of-range input is clamped with a message', async ({ page }) => {
  await page.goto('/curve-lab?security=BM-T-0005');
  const input = page.getByLabel('Parallel shift in basis points');
  await input.fill('900');
  await input.press('Enter');
  await input.blur();
  await expect(page.getByRole('alert').filter({ hasText: 'limited to ±300 bp' })).toBeVisible();
  await expect(input).toHaveValue('300');
});

test('curve lab: latest action wins when responses arrive out of order', async ({ page }) => {
  await page.route('**/api/v2/scenarios/evaluate', async (route) => {
    const body = route.request().postDataJSON();
    if (body.shockNodes[0].bp === 50) await new Promise((r) => setTimeout(r, 2000));
    await route.continue();
  });
  await page.goto('/curve-lab?security=BM-T-0005');
  await page.getByRole('button', { name: '+50', exact: true }).click();
  await page.waitForTimeout(500); // let the +50 request start
  await page.getByRole('button', { name: '+100', exact: true }).click();
  const valuation = page.locator('.lab-valuation');
  await expect(valuation.getByText('updating…')).toBeHidden({ timeout: 5000 });
  await page.waitForTimeout(2200); // the slow +50 response would have landed by now
  const shockCell = page.locator('table.data tbody tr', { hasText: /^\s*10Y/ }).locator('td').nth(3);
  await expect(shockCell).toHaveText('+100.0');
  const pct = await valuation.locator('tr', { hasText: 'Change %' }).locator('td').last().innerText();
  expect(Number(pct.replace('−', '-').replace('%', ''))).toBeLessThan(-5); // +100bp, not +50bp
});

test('curve lab: a failed valuation does not blank the curve charts', async ({ page }) => {
  await page.route('**/api/v2/scenarios/evaluate', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'internal_error', message: 'Internal server error', request_id: 'x' }),
    }),
  );
  await page.goto('/curve-lab?security=BM-T-0005');
  await expect(page.locator('.lab-valuation [role=alert]')).toContainText('Internal server error');
  await expect(page.getByText('Par curves: base, overlays and shocked')).toBeVisible();
  await expect(page.locator('table.data tbody tr').first()).toBeVisible();
});
