// Browser regression fixtures: source discovery/approval, without model or page collection calls.
(async () => {
  const { default: assert } = await import('node:assert/strict');
  const { pathToFileURL } = await import('node:url');
  const { resolve } = await import('node:path');
  const modulePath = process.env.PLAYWRIGHT_MODULE;
  const { chromium } = await import(modulePath ? pathToFileURL(`${modulePath}/index.mjs`).href : 'playwright');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const candidate = domain => ({ domain, pages: [{ title: `${domain} source page`, url: `https://${domain}/page`, provider: 'fixture' }] });
    const local = { provider: 'local', model: 'fixture:latest', allow_external: false };
    const catalog = { default: local, providers: [{ id: 'local', label: 'Local Ollama', available: true,
      models: [{ id: local.model, label: local.model, available: true, cost: { kind: 'local', label: 'Local / no API fee', note: 'Fixture', source_url: 'https://example.com' } }] }] };
    let mode = 'success', submitted = null, discoveryRequest = null, collectionRequests = 0;
    let release;
    let holdDiscovery = new Promise(resolve => { release = resolve; });
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let data = {}, status = 200;
      if (path === '/api/v1/auth/me') data = { id: 'fixture', email: 'fixture@example.test', name: 'Fixture' };
      else if (path === '/api/v1/me/models') data = catalog;
      else if (path === '/api/v1/me/source-discovery') {
        discoveryRequest = route.request().postDataJSON();
        await holdDiscovery;
        status = mode === 'error' ? 503 : 200;
        data = mode === 'error' ? { error: 'Fixture search unavailable. Retry discovery.' }
          : { domains: mode === 'empty' ? [] : [candidate('example.com'), candidate('other.org')], total: mode === 'empty' ? 0 : 2 };
      } else if (path === '/api/v1/collections' && route.request().method() === 'POST') {
        collectionRequests++;
        submitted = route.request().postDataJSON();
        status = mode === 'failed-run' ? 201 : 422;
        data = mode === 'failed-run' ? { id: 'failed-collection' } : { error: 'Fixture stops before model inference and collection.' };
      } else if (path === '/api/v1/collections/failed-collection/run') {
        data = { run_id: 'failed-run' };
      } else if (path === '/api/v1/runs/failed-run') {
        data = { id: 'failed-run', status: 'failed', current_stage: 'collecting', steps: [], error_message: 'Local Ollama: inference timed out.' };
      }
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
    const base = process.env.VERIFY_BASE_URL || 'http://127.0.0.1:3001';
    await page.goto(`${base}/collections/new`);
    const next = page.getByRole('button', { name: 'Continue', exact: true });
    const domainInput = page.getByLabel('Limit search to domains (optional)');
    await page.waitForFunction(() => document.querySelector('option[value="fixture:latest"]'));
    await page.getByLabel('Collection requirement').fill('Find robotics companies in Tamil Nadu');
    assert.equal(await domainInput.inputValue(), '');
    assert.equal(await page.getByLabel(/I have permission/).count(), 0);
    assert(await next.isEnabled(), 'Empty optional domains must not disable Continue');
    await domainInput.fill('https://example.com');
    assert(await next.isDisabled());
    await page.getByRole('alert').filter({ hasText: 'without https://' }).waitFor();
    await domainInput.fill('');
    await next.click();
    await page.getByText('Finding candidate sources...', { exact: true }).waitFor();
    const run = page.getByRole('button', { name: 'Run collection', exact: true });
    assert(await run.isDisabled());
    assert.equal(collectionRequests, 0);
    release(); holdDiscovery = Promise.resolve();
    await page.getByLabel('example.com', { exact: true }).waitFor();
    assert.deepEqual(discoveryRequest.domain_filters, []);
    assert(await run.isDisabled(), 'Discovery is not collection permission');
    const confirmation = page.getByLabel(/I have permission/);
    await confirmation.check();
    assert(await run.isEnabled());
    await page.getByLabel('other.org', { exact: true }).uncheck();
    assert.equal(await confirmation.isChecked(), false, 'Changing approved scope requires fresh confirmation');
    assert(await run.isDisabled());
    await confirmation.check();
    await page.screenshot({ path: resolve('../.runtime/source-review.png'), fullPage: true });
    await run.click();
    await page.getByRole('alert').filter({ hasText: 'Fixture stops before' }).waitFor();
    assert.equal(collectionRequests, 1);
    assert.deepEqual(submitted.source_policy, { basis: 'user_confirmed_permission', approved_domains: ['example.com'], domain_filters: [] });
    assert.deepEqual(submitted.model_selection, local);
    assert.deepEqual(submitted.discovery_sources, candidate('example.com').pages);

    mode = 'empty';
    await next.click();
    await page.getByText(/No candidate domains were returned/).waitFor();
    assert(await run.isDisabled());
    assert.equal(await confirmation.count(), 0);
    mode = 'error';
    await page.getByRole('button', { name: 'Find sources again' }).click();
    await page.getByRole('alert').filter({ hasText: 'Fixture search unavailable' }).waitFor();
    assert(await run.isDisabled());
    assert.equal(collectionRequests, 1);
    mode = 'success';
    await page.getByRole('button', { name: 'Find sources again' }).click();
    await confirmation.waitFor();
    assert.equal(await confirmation.isChecked(), false);
    await page.getByRole('button', { name: 'Back', exact: true }).click();
    await domainInput.fill('example.com');
    await next.click();
    await confirmation.waitFor();
    assert.deepEqual(discoveryRequest.domain_filters, ['example.com']);
    mode = 'failed-run';
    await confirmation.check();
    await run.click();
    await page.getByRole('alert').filter({ hasText: 'Local Ollama: inference timed out.' }).waitFor();
    assert.equal(await page.getByRole('link', { name: 'Inspect run' }).getAttribute('href'), '/runs/failed-run');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => document.querySelector('aside').getBoundingClientRect().right <= 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    assert.deepEqual(errors, []);
    console.log('PASS: blank-domain Continue, validation reasons, real discovery request, loading gate, explicit permission, scope reset, payload, empty/error/retry, restrictions, mobile layout');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
