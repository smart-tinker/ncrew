const { test, expect } = require('@playwright/test');

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required env var: ${name}`);
  return value;
}

const projectName = process.env.E2E_PROJECT_NAME || 'e2e-project';
const projectId = process.env.E2E_PROJECT_ID || projectName.toLowerCase().replace(/\s+/g, '-');
const projectPath = requireEnv('E2E_PROJECT_PATH');
const initialWorktreePrefix = process.env.E2E_WORKTREE_PREFIX || 'e2e-';
const modelFullName = process.env.E2E_MODEL_FULL_NAME || 'opencode/glm-4.7-free';

async function refreshModels(page) {
  const [dialog] = await Promise.all([
    page.waitForEvent('dialog'),
    page.getByRole('button', { name: 'Refresh Models' }).click()
  ]);
  expect(dialog.type()).toBe('alert');
  expect(dialog.message()).toContain('Models refreshed successfully');
  await dialog.accept();
}

async function ensureProjectExists(page) {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();

  const existingLink = page.getByRole('link', { name: new RegExp(`^${projectName}\\b`) });
  if (await existingLink.isVisible().catch(() => false)) return;

  await page.getByRole('button', { name: '+ Add Project' }).click();

  await page.getByPlaceholder('Project Name').fill(projectName);
  await page.getByPlaceholder('Project Path (absolute)').fill(projectPath);
  await page.getByPlaceholder(/Worktree Prefix/).fill(initialWorktreePrefix);

  await page.getByRole('button', { name: 'Add Project', exact: true }).click();

  await expect(existingLink).toBeVisible();
}

async function gotoProject(page) {
  await page.goto(`/project/${projectId}`);
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible();
  await expect(page.getByText(projectPath)).toBeVisible();
}

function taskCard(page, title) {
  const heading = page.getByRole('heading', { name: title });
  return heading.locator('xpath=ancestor::div[contains(@class,"card")][1]');
}

test.describe.serial('NCrew UI E2E (no AI)', () => {
  test('Projects: refresh models + add project', async ({ page }) => {
    await ensureProjectExists(page);
    await refreshModels(page);

    await page.getByRole('link', { name: new RegExp(`^${projectName}\\b`) }).click();
    await expect(page.getByRole('heading', { name: projectName })).toBeVisible();

    await expect(page.getByRole('heading', { name: 'E2E Spec Run' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'E2E Stop (Long Run)' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'E2E Next Stage' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'E2E Last Stage' })).toBeVisible();
  });

  test('Task: run spec stage -> logs/timeline -> Done', async ({ page }) => {
    await gotoProject(page);

    const spec = taskCard(page, 'E2E Spec Run');
    await expect(spec.locator('.stage-badge')).toHaveText('Specification');
    await expect(spec.locator('.status-badge')).toHaveText('New');

    await spec.getByRole('button', { name: 'Run' }).click();
    const runModal = page.locator('.modal').filter({ hasText: 'Run Task: E2E Spec Run' });
    await expect(runModal).toBeVisible();

    const modelSelect = runModal.getByRole('combobox');
    await expect(modelSelect).toHaveValue(modelFullName);
    await runModal.getByRole('button', { name: 'Run' }).click();

    await expect(spec.getByRole('button', { name: 'Stop' })).toBeVisible();

    await spec.getByRole('heading', { name: 'E2E Spec Run' }).click();
    const detailModal = page.locator('.modal').filter({ hasText: 'Timeline:' });
    await expect(detailModal.getByRole('heading', { name: 'E2E Spec Run' })).toBeVisible();

    const logPre = detailModal.locator('pre');
    await expect(logPre).toContainText('[NCrew] Stage: Specification');
    await expect(logPre).toContainText(`[NCrew] Using model: ${modelFullName}`);
    await expect(logPre).toContainText('.ncrew/templates/spec.md');
    await expect(logPre).not.toContainText('~/.ncrew/templates/spec.md');

    await expect(logPre).toContainText('[NCrew] Exit code: 0', { timeout: 30_000 });
    await expect(detailModal.locator('.timeline-entry')).toHaveCount(1);

    await detailModal.getByRole('button', { name: 'Close' }).click();

    await page.reload();
    await expect(taskCard(page, 'E2E Spec Run').locator('.status-badge')).toHaveText('Done');
    await expect(taskCard(page, 'E2E Spec Run').getByRole('button', { name: 'Next Stage' })).toBeVisible();
  });

  test('Project: edit worktree prefix warns when worktrees exist', async ({ page }) => {
    await gotoProject(page);

    await page.getByRole('button', { name: 'Edit' }).click();
    const editModal = page.locator('.modal');
    await expect(editModal.getByRole('heading', { name: 'Edit Project' })).toBeVisible();

    // 0: name, 1: worktreePrefix
    await editModal.locator('input').nth(1).fill('new-');

    const [confirm] = await Promise.all([
      page.waitForEvent('dialog'),
      editModal.getByRole('button', { name: 'Save' }).click()
    ]);
    expect(confirm.type()).toBe('confirm');
    expect(confirm.message()).toContain('Changing worktree prefix');
    await confirm.accept();

    await expect(page.getByText('Worktree prefix: new-')).toBeVisible();
  });

  test('Task: Next Stage advances stage and resets status', async ({ page }) => {
    await gotoProject(page);

    const next = taskCard(page, 'E2E Next Stage');
    await expect(next.locator('.stage-badge')).toHaveText('Plan');
    await expect(next.locator('.status-badge')).toHaveText('Done');

    await next.getByRole('button', { name: 'Next Stage' }).click();

    await expect(next.locator('.stage-badge')).toHaveText('Implementation');
    await expect(next.locator('.status-badge')).toHaveText('New');
    await expect(next.getByRole('button', { name: 'Next Stage' })).toHaveCount(0);
  });

  test('Task: Stop cancels long-running run and marks Failed', async ({ page }) => {
    await gotoProject(page);

    const stopTask = taskCard(page, 'E2E Stop (Long Run)');
    await stopTask.getByRole('button', { name: 'Run' }).click();

    const runModal = page.locator('.modal').filter({ hasText: 'Run Task: E2E Stop (Long Run)' });
    await expect(runModal).toBeVisible();
    await runModal.getByRole('button', { name: 'Run' }).click();

    await expect(stopTask.getByRole('button', { name: 'Stop' })).toBeVisible();
    await expect(stopTask.getByText(/\d\d:\d\d:\d\d/)).toBeVisible();

    await stopTask.getByRole('button', { name: 'Stop' }).click();
    await expect(stopTask.locator('.status-badge')).toHaveText('Failed');
  });

  test('Task: No Next Stage on Verification stage', async ({ page }) => {
    await gotoProject(page);

    const last = taskCard(page, 'E2E Last Stage');
    await expect(last.locator('.stage-badge')).toHaveText('Verification');
    await expect(last.locator('.status-badge')).toHaveText('Done');
    await expect(last.getByRole('button', { name: 'Next Stage' })).toHaveCount(0);
  });
});
