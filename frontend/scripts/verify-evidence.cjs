// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright package.
(async () => {
  const { default: assert } = await import("node:assert/strict");
  const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ? `${process.env.PLAYWRIGHT_MODULE}/index.mjs` : "playwright");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") console.error("Browser:", message.text()); });
    page.on("requestfailed", (request) => console.error("Failed request:", request.url(), request.failure()?.errorText));
    const id = "11111111-1111-4111-8111-111111111111";
    const ds = "22222222-2222-4222-8222-222222222222";
    const collection = { id, title: "Evidence regression fixture", prompt: "Find companies", status: "completed", updated_at: "2026-09-29T10:00:00Z", data_contract: { entity_type: "company", fields: [], constraints: [], allowed_domains: [] } };
    const record = { id: "fixture-record", canonical_name: "Fixture Robotics", status: "needs_review", confidence_score: .43,
      primary_attributes: { industry: "robotics", location: "Chennai", provenance: { source_urls: ["https://example.com/evidence"], agreement_rate: 0,
        field_evidence: [{ field_name: "location", verbatim_quote: "Fixture Robotics is based in Chennai.", extracted_value: "Chennai", source_url: "https://example.com/evidence", char_start: 100, char_end: 136 }],
        factors: [{ factor_name: "grounding_score", score: .31, weight: .25, contribution: .0775 }] } }, confidence_breakdown: { grounding_score: .31 } };
    let fail = false;
    await page.route("**/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
      if (path === "/v1/auth/me") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "fixture-user", name: "Fixture User", email: "fixture@example.test" }) });
        return;
      }
      const data = path === "/v1/collections" ? { data: [collection] }
        : path === `/v1/collections/${id}` ? collection
        : path === "/v1/datasets" ? { data: [{ id: ds, collection_id: id, name: "Fixture results", created_at: "2026-09-29T10:00:00Z", record_count: 1, avg_confidence: .43 }] }
        : path === `/v1/datasets/${ds}/records` ? { data: [record] }
        : path === "/v1/sources" ? { data: [{ id: "s", domain: "example.com", source_type: "general", enabled: true, extraction_success_rate: 0 }] }
        : {};
      await route.fulfill({ status: fail ? 503 : 200, contentType: "application/json", body: JSON.stringify(fail ? { error: "Fixture API unavailable" } : data) });
    });
    const base = process.env.VERIFY_BASE_URL || "http://127.0.0.1:3001";
    await page.goto(`${base}/collections/${id}`);
    try {
      await page.getByRole("button", { name: "Fixture Robotics", exact: true }).click({ timeout: 20000 });
    } catch (error) {
      console.error("Rendered page:", (await page.locator("body").innerText()).slice(0, 2500), errors);
      throw error;
    }
    const drawer = page.getByRole("dialog");
    await drawer.waitFor();
    const text = await drawer.innerText();
    assert(text.includes("43%"));
    assert(text.includes("0%"));
    assert(text.includes("31%"));
    assert(text.includes("Not measured"));
    assert(text.includes("Not checked"));
    assert(text.includes("100–136"));
    assert(!text.includes("92%"));
    assert(!text.includes("200 OK"));
    await page.getByRole("button", { name: "Close evidence drawer" }).click();
    await page.getByRole("tab", { name: /Sources/ }).click();
    assert((await page.getByRole("tabpanel").innerText()).includes("Not checked"));
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.goto(`${base}/sources`);
    await page.getByText("Not checked", { exact: true }).waitFor();
    assert(!(await page.locator("main").innerText()).includes("200 OK"));
    await page.goto(`${base}/history`);
    await page.getByRole("link", { name: "Evidence regression fixture", exact: true }).waitFor();
    assert(!(await page.locator("main").innerText()).includes("0 ms"));
    fail = true;
    await page.goto(`${base}/collections/${id}`);
    await page.locator("main").getByRole("alert").waitFor();
    assert((await page.locator("main").getByRole("alert").innerText()).includes("Fixture API unavailable"));
    assert.equal(await page.getByText("Sponsor prospects for robotics event").count(), 0);
    await page.goto(`${base}/history`);
    await page.locator("main").getByRole("alert").waitFor();
    assert((await page.locator("main").getByRole("alert").innerText()).includes("Fixture API unavailable"));
    assert.equal(await page.getByText("Sponsor prospects for robotics event").count(), 0);
    assert.deepEqual(errors, []);
    console.log("PASS: measured confidence, unknown health, exact evidence, tabs, mobile width, and API failure without mock substitution");
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
