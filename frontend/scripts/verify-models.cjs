// Browser fixtures intercept every API call: never send collection data to NVIDIA.
(async () => {
  const { default: assert } = await import("node:assert/strict");
  const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ? `${process.env.PLAYWRIGHT_MODULE}/index.mjs` : "playwright");
  const browser = await chromium.launch({ headless: true, timeout: 30000 });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const id = "11111111-1111-4111-8111-111111111111";
  const ds = "22222222-2222-4222-8222-222222222222";
  let submitted, failCreate = false, failModels = false, completed = false, catalogRequests = 0;
  let catalog = { default: { provider: "local", model: "qwen2.5-coder:1.5b-instruct", allow_external: false }, providers: [
    { id: "local", label: "Local · Ollama", available: true, models: [
      { id: "qwen2.5-coder:1.5b-instruct", label: "Qwen 2.5 Coder 1.5B · lightweight", available: true },
      { id: "qwen2.5-coder:7b", label: "Qwen 2.5 Coder 7B · larger", available: true },
      { id: "qwen2.5-coder:1.5b-base", label: "qwen2.5-coder:1.5b-base", available: true }] },
    { id: "nvidia", label: "NVIDIA · hosted", available: true, models: [
      { id: "meta/llama-3.3-70b-instruct", label: "Llama 3.3 70B", available: true },
      { id: "meta/llama-3.1-8b-instruct", label: "Llama 3.1 8B", available: true },
      { id: "qwen/new-chat-model", label: "qwen/new-chat-model", available: true },
      { id: "nvidia/embed-qa-4", label: "nvidia/embed-qa-4", available: false, reason: "Embedding or reranking model; cannot run a collection." }] },
  ] };
  if (process.env.VERIFY_LIVE_MODEL_CATALOG === "1") {
    // Only GET catalog metadata. All collection writes/inference remain intercepted.
    const response = await fetch("http://127.0.0.1:7000/models");
    assert(response.ok);
    catalog = await response.json();
  }
  const localModels = catalog.providers.find((provider) => provider.id === "local").models;
  const nvidiaModels = catalog.providers.find((provider) => provider.id === "nvidia").models;
  const chosenNvidia = nvidiaModels.find((model, index) => index > 0 && model.available && !["meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct"].includes(model.id)).id;
  const collection = { id, title: "Provider selection fixture", prompt: "Find robotics companies", status: "completed", updated_at: new Date().toISOString(), data_contract: { entity_type: "company", fields: [], constraints: [], allowed_domains: [] } };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let status = 200, data = {};
    if (path === "/api/v1/auth/me") data = { id: "fixture-user", name: "Fixture User", email: "fixture@example.test" };
    else if (path === "/api/v1/me/models") { catalogRequests++; status = failModels ? 503 : 200; data = failModels ? { error: "Model catalog unavailable" } : catalog; }
    else if (path === "/api/v1/collections" && route.request().method() === "POST") {
      submitted = route.request().postDataJSON(); status = failCreate ? 422 : 201;
      data = failCreate ? { error: "Selected provider unavailable. Try another model." } : collection;
    } else if (path === `/api/v1/collections/${id}/run`) data = { run_id: "fixture-run", status: "pending" };
    else if (path === "/api/v1/runs/fixture-run") data = { status: completed ? "completed" : "pending", current_stage: "extracting" };
    else if (path === `/api/v1/collections/${id}`) data = collection;
    else if (path === "/api/v1/collections") data = { data: [collection] };
    else if (path === "/api/v1/datasets") data = { data: [{ id: ds, collection_id: id, name: "Fixture results", created_at: new Date().toISOString(), record_count: 1 }] };
    else if (path === `/api/v1/datasets/${ds}/records`) data = { data: [{ id: "record", canonical_name: "Fixture Robotics", status: "draft", primary_attributes: {} }] };
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
  });
  const base = process.env.VERIFY_BASE_URL || "http://127.0.0.1:3001";
  try {
    await page.goto(`${base}/collections/new`);
    const provider = page.getByLabel("Provider", { exact: true });
    const model = page.getByLabel("Model", { exact: true });
    const next = page.getByRole("button", { name: "Continue", exact: true });
    await page.getByText(`${localModels.length} installed models · ${localModels.filter((item) => item.available).length} for collections`, { exact: true }).waitFor();
    assert.equal(await model.inputValue(), "qwen2.5-coder:1.5b-instruct");
    assert.equal(await model.locator("option").count(), localModels.length);
    await model.selectOption("qwen2.5-coder:1.5b-base");
    assert.equal(await model.inputValue(), "qwen2.5-coder:1.5b-base");
    const requestsBeforeRefresh = catalogRequests;
    const refresh = page.getByRole("button", { name: "Refresh models", exact: true });
    localModels.push({ id: "newly-installed:latest", label: "newly-installed:latest", available: true });
    await refresh.click();
    await page.waitForFunction(() => document.querySelector('option[value="newly-installed:latest"]'));
    assert.equal(catalogRequests, requestsBeforeRefresh + 1);
    assert.equal(await model.inputValue(), "qwen2.5-coder:1.5b-base");
    await model.selectOption("newly-installed:latest");
    localModels.pop();
    await refresh.click();
    await page.waitForFunction(() => document.querySelector('option[value="newly-installed:latest"]')?.disabled);
    assert.equal(await model.inputValue(), "newly-installed:latest");
    assert(await next.isDisabled());
    await model.selectOption("qwen2.5-coder:1.5b-base");
    await provider.focus();
    await provider.press("Space");
    await provider.press("Escape");
    assert.equal(await provider.evaluate((el) => document.activeElement === el), true);
    await provider.selectOption("nvidia");
    assert.equal(await model.locator("option").count(), nvidiaModels.length);
    assert.equal(await model.locator("option:disabled").count(), nvidiaModels.filter((item) => !item.available).length);
    assert(await next.isDisabled());
    await page.getByRole("checkbox", { name: /Allow NVIDIA/ }).check();
    assert(await next.isEnabled());
    await model.selectOption(chosenNvidia);
    assert(await next.isDisabled());
    await page.getByRole("checkbox", { name: /Allow NVIDIA/ }).check();
    await page.screenshot({ path: "/tmp/datavault-model-selector-desktop.png", fullPage: true });
    await next.click();
    assert((await page.locator("main").innerText()).includes(chosenNvidia));
    failCreate = true;
    await page.getByRole("button", { name: "Run collection", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "Selected provider unavailable" }).waitFor();
    assert.equal(submitted.model_selection.provider, "nvidia");
    assert.equal(submitted.model_selection.model, chosenNvidia);
    assert.equal(submitted.model_selection.allow_external, true);
    assert.equal(await model.inputValue(), chosenNvidia);
    await provider.selectOption("local");
    failCreate = false;
    await next.click();
    await page.getByRole("button", { name: "Run collection", exact: true }).click();
    await page.locator("li").filter({ hasText: "Extract records" }).locator("svg.animate-spin").waitFor();
    await page.waitForTimeout(5500);
    assert.equal(await page.locator("li").filter({ hasText: "Save results" }).locator("svg").count(), 0);
    assert.equal(submitted.model_selection.provider, "local");
    assert.equal(submitted.model_selection.allow_external, false);
    completed = true;
    await page.waitForURL(`**/collections/${id}`);
    failModels = true;
    await page.goto(`${base}/collections/new`);
    await page.getByRole("alert").filter({ hasText: "Model catalog unavailable" }).waitFor();
    assert(await next.isDisabled());
    failModels = false;
    await page.getByRole("button", { name: "Retry models" }).click();
    await provider.selectOption("nvidia");
    assert(await next.isDisabled()); // no consent persisted across visits
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "/tmp/datavault-model-selector-mobile.png", fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await model.focus();
    await model.press("Space");
    await model.press("Escape");
    assert.deepEqual(errors, []);
    console.log(`PASS: all ${nvidiaModels.length} NVIDIA and ${localModels.length} Ollama models rendered, refresh/add/remove, new model payload, consent/reset, recovery, progress, keyboard and mobile`);
  } catch (error) {
    console.error("Rendered UI:", (await page.locator("body").innerText()).slice(0, 5000));
    console.error("Page errors:", errors);
    await page.screenshot({ path: "/tmp/datavault-model-selector-failure.png", fullPage: true });
    throw error;
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
