import { expect, test } from '@playwright/test';

test.describe('Bond Explorer', () => {
  test('filter, sort, open a bond, and come back to the same view', async ({ page }) => {
    await page.goto('/bonds');
    await expect(page.locator('.stat-strip')).toContainText('Bonds');
    await page.locator('.select-pill', { hasText: 'Rating' }).locator('select').selectOption('BBB');
    await expect(page).toHaveURL(/rating=BBB/);
    await expect(page.locator('.chip-active')).toContainText('BBB');
    const pills = page.locator('tbody .pill');
    await expect(pills.first()).toHaveText('BBB');
    expect(new Set(await pills.allInnerTexts())).toEqual(new Set(['BBB']));

    await page.getByRole('button', { name: /Spread bp/ }).click();
    await expect(page).toHaveURL(/sort=-g_spread_bp/);
    await expect
      .poll(async () => {
        const spreads = (await page.locator('tbody tr td:nth-child(10)').allInnerTexts()).map(Number);
        return spreads.length > 1 && spreads.every((v, i) => i === 0 || spreads[i - 1] >= v);
      })
      .toBe(true);

    await page.locator('tbody tr').first().click();
    await expect(page).toHaveURL(/\/bonds\/BM-C-\d+$/);
    await expect(page.locator('.kpi', { hasText: 'Yield to maturity' }).locator('b')).toHaveText(/\d+\.\d{3}%/);
    await page.getByRole('link', { name: '← Bond Explorer' }).click();
    await expect(page).toHaveURL(/rating=BBB/);
    await expect(page).toHaveURL(/sort=-g_spread_bp/);
  });

  test('numbers are formatted, not raw', async ({ page }) => {
    await page.goto('/bonds?bond_type=corporate');
    const coupon = page.locator('tbody tr').first().locator('td').nth(3);
    await expect(coupon).toHaveText(/^\s*\d+\.\d{3}\s*$/);
  });

  test('search with no matches shows an empty state', async ({ page }) => {
    await page.goto('/bonds');
    await page.getByLabel('Search bonds').fill('zzzz-no-such-bond');
    await expect(page.getByText('No bonds match these filters.')).toBeVisible();
    await page.getByRole('button', { name: 'Clear filters' }).click();
    await expect(page.locator('tbody tr.clickable').first()).toBeVisible();
  });
});

test.describe('Yield Curve', () => {
  test('compare two dates with presets and a custom date; gaps stay gaps', async ({ page }) => {
    await page.goto('/yield-curve');
    await expect(page.locator('.tile').first()).toContainText('%');
    await page.getByRole('button', { name: '1Y', exact: true }).click();
    await expect(page).toHaveURL(/compare=1Y/);
    await expect(page.locator('table.data thead')).toContainText('2025-11-06');

    await page.getByLabel('Compare date').fill('2024-11-06');
    await page.getByLabel('Compare date').dispatchEvent('change');
    await expect(page.locator('table.data thead')).toContainText('2024-11-06');
    const row = page.locator('table.data tbody tr', { hasText: '1.5M' });
    await expect(row.locator('td').nth(2)).toHaveText('n/a');
    await expect(row.locator('td').nth(3)).toHaveText('n/a');
    await expect(page.locator('.spread-card').first()).toContainText('bp');
  });
});

test.describe('Price Simulator', () => {
  test('moving the yield reprices the bond and shows the duration error', async ({ page }) => {
    await page.goto('/simulator?bond=BM-T-0007');
    await page.getByRole('button', { name: '+100', exact: true }).click();
    await expect(page).toHaveURL(/shift=100/);
    const price = page.locator('.kpi', { hasText: 'Price' }).first().locator('small');
    await expect(price).toHaveText(/^−\d+\.\d{2} \(−\d+\.\d{2}%\)$/);
    // duration alone underestimates the price (convexity): error is negative
    await expect(page.locator('.kpi', { hasText: 'Duration estimate' }).locator('small')).toHaveText(/off by −/);

    await page.getByRole('button', { name: '−100', exact: true }).click();
    await expect(page.locator('.kpi', { hasText: 'Price' }).first().locator('small')).toHaveText(/^\+/);
  });

  test('exact input is clamped to ±300 bp', async ({ page }) => {
    await page.goto('/simulator?bond=BM-T-0007');
    const input = page.locator('input.bp-input');
    await input.fill('900');
    await input.dispatchEvent('change');
    await expect(page.locator('.big-shift')).toContainText('+300 bp');
  });

  test('a failed calculation shows an error without breaking the controls', async ({ page }) => {
    await page.route('**/price-yield*', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'internal_error', message: 'Internal server error' }),
      }),
    );
    await page.goto('/simulator?bond=BM-T-0007');
    await expect(page.getByRole('alert')).toContainText('Internal server error');
    await expect(page.getByLabel('Change in yield in basis points')).toBeVisible();
    await expect(page.getByText('What am I looking at?')).toBeVisible();
  });
});

test('old links redirect to the new pages', async ({ page }) => {
  await page.goto('/curve-lab');
  await expect(page).toHaveURL(/\/yield-curve/);
  await page.goto('/terminal/security/BM-C-0001');
  await expect(page).toHaveURL(/\/bonds\/BM-C-0001/);
});
