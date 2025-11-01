import { test, expect } from '@playwright/test';

// Test data based on RB_TESTING.md fixtures
const user1 = {
  email: 'testuser1@example.com',
  password: 'test jwt', // frontend expects field name 'jwt' but UI labels it Password
  room: '500',
};

const user2 = {
  email: 'testuser2@example.com',
  password: 'test jwt',
  room: '501',
};

test.describe('Room Swap Workflow', () => {
  test('user1 generates code; user2 redeems; rooms are swapped', async ({ page, browser }) => {
    // --- User 1 logs in and generates a swap code ---
    await page.goto('/'); // baseURL set to http://frontend:3000

    await page.getByLabel('Email:').fill(user1.email);
    await page.getByLabel('Password:').fill(user1.password);
    await page.getByRole('button', { name: 'Submit' }).click();

    // Wait for navigation to complete
    await page.waitForURL('**/rooms', { timeout: 10000 });

    // Wait for the table structure to exist (indicates data has loaded)
    await page.waitForSelector('table', { timeout: 10000 });

    // Wait for the My Rooms table to be visible
    await expect(page.getByText('My Rooms')).toBeVisible({ timeout: 10000 });

    // Find User 1's room row and click CreateSwapCode
    const user1Row = page.locator('table tbody tr').filter({ hasText: user1.room });
    await expect(user1Row).toHaveCount(1, { timeout: 30000 });
    await user1Row.getByRole('button', { name: 'CreateSwapCode' }).click();

    // Modal opens and shows the generated code line "Swap Code: <phrase>"
    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    const modalText = await modal.textContent();
    // phrasing() returns CamelCase with optional digits; capture alphanumerics
    const match = modalText?.match(/Swap Code:\s*([A-Za-z0-9]+)/);
    expect(match && match[1]).toBeTruthy();
    const swapCode = match![1];

    // --- User 2 logs in and redeems the code ---
    const user2Context = await browser.newContext();
    const user2Page = await user2Context.newPage();

    await user2Page.goto('/');
    await user2Page.getByLabel('Email:').fill(user2.email);
    await user2Page.getByLabel('Password:').fill(user2.password);
    await user2Page.getByRole('button', { name: 'Submit' }).click();

    // Wait for navigation to complete
    await user2Page.waitForURL('**/rooms', { timeout: 10000 });

    // Wait for the table structure to exist (indicates data has loaded)
    await user2Page.waitForSelector('table', { timeout: 10000 });

    await expect(user2Page.getByText('My Rooms')).toBeVisible({ timeout: 10000 });

    // On user2's own room row, click EnterSwapCode, fill the code, submit
    const user2Row = user2Page.locator('table tbody tr').filter({ hasText: user2.room });
    await expect(user2Row).toHaveCount(1, { timeout: 30000 });
    await user2Row.getByRole('button', { name: 'EnterSwapCode' }).click();

    const enterModal = user2Page.getByRole('dialog');
    await expect(enterModal).toBeVisible();
    await user2Page.getByLabel('Input the SwapCode sent to you').fill(swapCode);
    await user2Page.getByRole('button', { name: 'Submit' }).click();

    // After redeem, user2 should now have room 500 visible
    await expect(user2Page.locator('table tbody tr').filter({ hasText: user1.room })).toHaveCount(1, { timeout: 30000 });

    // Refresh user1 and verify their My Rooms table shows user2's old room
    await page.reload();
    await expect(page.locator('table tbody tr').filter({ hasText: user2.room })).toHaveCount(1, { timeout: 30000 });

    await user2Context.close();
  });
});
