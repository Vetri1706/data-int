// Browser integration fixtures only. No keys, provider calls or collected data.
(async () => {
  const { default: assert } = await import('node:assert/strict');
  const { pathToFileURL } = await import('node:url');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const modulePath = process.env.PLAYWRIGHT_MODULE;
  const { chromium } = await import(modulePath ? pathToFileURL(`${modulePath}/index.mjs`).href : 'playwright');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(12000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const modelRow = (id, kind, label) => ({ id, label: id, available: true, cost: { kind, label, note: 'Fixture pricing; not a billing guarantee.', source_url: 'https://example.com/pricing' } });
    const catalog = { default: { provider: 'glm', model: 'glm-4.5-flash', allow_external: false }, providers: [
      { id: 'glm', label: 'GLM (Z.ai)', available: true, models: [modelRow('glm-5', 'paid', 'Paid'), modelRow('glm-4.7-flash', 'free', 'Free'), modelRow('glm-4.5-flash', 'free', 'Free')] },
      { id: 'groq', label: 'Groq', available: true, models: [modelRow('openai/gpt-oss-20b', 'free_tier', 'Free tier available')] },
      { id: 'huggingface', label: 'Hugging Face', available: true, models: [modelRow('org/paid:host', 'credits', 'Credits / paid'), modelRow('org/free:host', 'free', 'Free')] },
      { id: 'local', label: 'Local Ollama', available: false, reason: 'Cannot reach Ollama.', models: [] },
      ...['nvidia', 'gemini', 'openrouter'].map(id => ({ id, label: id, available: false, reason: `Add ${id.toUpperCase()}_API_KEY to .env.`, models: [] })),
    ] };
    let failModels = false, catalogRequests = 0, submitted = null;
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let status = 200, data = {};
      if (path === '/api/v1/auth/me') data = { id: 'fixture-user', email: 'fixture@example.test', name: 'Fixture' };
      else if (path === '/api/v1/runs/failed-local') data = { id: 'failed-local', collection_id: 'retry-source', status: 'failed', records_verified: 0, error_message: 'Local inference timed out' };
      else if (path === '/api/v1/runs/failed-local/history') data = { data: [], review_candidates: [] };
      else if (path === '/api/v1/datasets') data = { data: [] };
      else if (path === '/api/v1/collections/retry-source') data = { prompt: 'Find EV component suppliers in India', data_contract: { source_policy: { domain_filters: ['example.com'] } } };
      else if (path === '/api/v1/me/models') {
        catalogRequests++;
        status = failModels ? 503 : 200;
        data = failModels ? { error: 'Model catalog unavailable' } : catalog;
      } else if (path === '/api/v1/me/source-discovery') {
        data = { domains: [{ domain: 'example.com', pages: [{ title: 'Fixture source', url: 'https://example.com/source', provider: 'fixture' }] }], total: 1 };
      } else if (path === '/api/v1/collections' && route.request().method() === 'POST') {
        submitted = route.request().postDataJSON();
        // The chosen route disappears while collection creation is failing.
        catalog.providers.find(p => p.id === 'huggingface').models.pop();
        status = 422;
        data = { error: 'Fixture provider unavailable. Try another model.' };
      }
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
    const base = process.env.VERIFY_BASE_URL || 'http://127.0.0.1:3107';
    await page.goto(`${base}/collections/new`);
    const provider = page.getByLabel('Provider', { exact: true });
    const model = page.getByLabel('Model', { exact: true });
    const next = page.getByRole('button', { name: 'Continue', exact: true });
    await page.waitForFunction(() => [...document.querySelectorAll('select')].some(s => s.value === 'glm'));
    assert.equal(await model.inputValue(), 'glm-4.5-flash');
    assert.equal(await provider.locator('option').count(), 7);
    assert.equal(await provider.locator('option:disabled').count(), 4);
    assert.deepEqual(await model.locator('option').evaluateAll(options => options.map(o => o.value)), ['glm-4.5-flash', 'glm-4.7-flash', 'glm-5']);
    assert((await model.locator('option').first().innerText()).includes('Free'));
    await page.getByLabel('Collection requirement').fill('Find robotics companies with official source evidence');
    // Domains and source permission are not prerequisites for Continue.
    assert.equal(await page.getByLabel('Limit search to domains (optional)').inputValue(), '');
    assert.equal(await page.getByLabel(/I have permission/).count(), 0);
    assert(await next.isDisabled());
    await page.getByRole('checkbox', { name: /Allow GLM/ }).check();
    assert(await next.isEnabled());
    await model.selectOption('glm-4.7-flash');
    assert(await next.isDisabled());
    await provider.selectOption('groq');
    assert((await model.locator('option').innerText()).includes('Free tier available'));
    await page.getByRole('checkbox', { name: /Allow Groq/ }).check();
    await provider.selectOption('huggingface');
    assert(await next.isDisabled());
    assert.equal(await model.inputValue(), 'org/free:host');
    assert.equal(await model.locator('option').first().getAttribute('value'), 'org/free:host');
    await model.selectOption('org/free:host');
    await page.getByRole('checkbox', { name: /Allow Hugging Face/ }).check();
    await next.click();
    await page.getByText('Processing: Hugging Face', { exact: false }).waitFor();
    await page.getByLabel(/I have permission/).check();
    await page.getByRole('button', { name: 'Run collection', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Fixture provider unavailable' }).waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('select')].some(s => s.value === 'huggingface' && !s.disabled));
    assert.deepEqual(submitted.model_selection, { provider: 'huggingface', model: 'org/free:host', allow_external: true });
    assert.equal(await provider.inputValue(), 'huggingface');
    // A disappearing selection is blocked, never silently switched to another model.
    assert.equal(await model.inputValue(), 'org/free:host');
    assert.equal(await model.locator('option[value="org/free:host"]').isDisabled(), true);
    const beforeRefresh = catalogRequests;
    await page.getByRole('button', { name: 'Refresh models', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('option[value="org/free:host"]')?.disabled);
    assert.equal(catalogRequests, beforeRefresh + 1);
    assert(await next.isDisabled());
    assert.equal(await model.inputValue(), 'org/free:host');
    // Local Ollama is available only when its catalog reports installed models.
    const local = catalog.providers.find(p => p.id === 'local');
    local.available = true; local.reason = null; local.default_model = 'z-instruction:latest';
    local.models = [modelRow('a-first:latest', 'local', 'Local / no API fee'), modelRow('z-instruction:latest', 'local', 'Local / no API fee')];
    await page.getByRole('button', { name: 'Refresh models', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('option[value="local"]').disabled);
    await provider.selectOption('local');
    assert.equal(await model.inputValue(), 'z-instruction:latest');
    assert.equal(await page.getByRole('checkbox', { name: /^Allow / }).count(), 0);
    assert(await next.isEnabled());
    failModels = true;
    await page.getByRole('button', { name: 'Refresh models', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Model catalog unavailable' }).waitFor();
    assert(await next.isDisabled());
    failModels = false;
    await page.getByRole('button', { name: 'Retry models', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('select').disabled);
    await provider.selectOption('glm');
    await model.selectOption('glm-4.5-flash');
    await page.screenshot({ path: join(tmpdir(), 'datavault-providers-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    // Wait for the existing sidebar's responsive exit transition before capture.
    await page.waitForFunction(() => document.querySelector('aside').getBoundingClientRect().right <= 1);
    await page.screenshot({ path: join(tmpdir(), 'datavault-providers-mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await model.focus(); await model.press('Space'); await model.press('Escape');
    await page.goto(`${process.env.VERIFY_BASE_URL || 'http://127.0.0.1:3001'}/runs/failed-local`);
    await page.getByRole('button', { name: 'Retry with configured local model' }).click();
    await page.waitForURL('**/collections/new?**');
    await page.waitForFunction(() => [...document.querySelectorAll('select')].some(s => s.value === 'z-instruction:latest'));
    assert.equal(await page.getByLabel('Provider', { exact: true }).inputValue(), 'local');
    assert.equal(await page.getByLabel('Limit search to domains (optional)').inputValue(), 'example.com');
    assert.equal(await page.locator('textarea').inputValue(), 'Find EV component suppliers in India');
    assert.equal(await page.getByRole('checkbox', { name: /^Allow / }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: seven providers, configuration gates, free-first order, tier labels, consent/reset, pinned HF payload, removed-model blocking, local Ollama, refresh/recovery and mobile width');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
