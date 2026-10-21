import { test, expect } from '@playwright/test';

test('original pages, navigation, and live operator connection', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  expect((await request.get('/api/healthz')).ok()).toBeTruthy();
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Manage social sales');
  await expect(page.getByText('Connected (Healthy)')).toBeVisible();
  await page.getByRole('link', { name: /Launch Dashboard/ }).click();
  await expect(page).toHaveURL(/\/dashboard\/integration-hub$/);
  for (const route of ['knowledge-brain', 'employee-roster', 'operator-workbench']) {
    await page.locator(`a[href="/dashboard/${route}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`/dashboard/${route}$`));
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  }
  await expect(page.getByText('WebSocket Live')).toBeVisible();
  for (const route of ['/privacy', '/terms']) {
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page).not.toHaveTitle('JOY - Multi-Tenant Digital Workforce Platform');
  }
  expect(errors).toEqual([]);
});

test('employee guardrails save and survive a reload', async ({ page, request }) => {
  const workspace = await request.get('/api/v1/tenant/me');
  expect(workspace.ok()).toBeTruthy();
  const { id: tenant } = await workspace.json();
  const url = `/api/v1/tenant/${tenant}/agents`;
  const response = await request.get(url);
  expect(response.ok()).toBeTruthy();
  const { agents } = await response.json();
  expect(agents.length).toBeGreaterThanOrEqual(2);
  const original = agents[0];
  const newCap = original.max_discount_pct === 15 ? 10 : 15;
  try {
    await page.goto('/dashboard/employee-roster');
    await expect(page.getByText(original.name, { exact: true })).toBeVisible();
    // Each employee has a tone slider followed by a discount slider.
    await page.locator('input[type="range"]').nth(1).fill(String(newCap));
    await page.getByRole('button', { name: /Save/ }).first().click();
    await expect(page.getByText(/Saved guardrails for/)).toBeVisible();
    await page.reload();
    await expect(page.locator('input[type="range"]').nth(1)).toHaveValue(String(newCap));
    const updated = await (await request.get(url)).json();
    expect(updated.agents.find((a: { id: string }) => a.id === original.id).max_discount_pct).toBe(newCap);
  } finally {
    const restored = await request.put(`${url}/${original.id}`, {
      data: { max_discount_pct: original.max_discount_pct },
    });
    expect(restored.ok()).toBeTruthy();
  }
});

test('homepage retains mobile layout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.screenshot({ path: 'generated-artifacts/home-mobile.jpg', fullPage: true });
});
