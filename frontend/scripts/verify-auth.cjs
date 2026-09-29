// Only run against a disposable database/API. Creates fixture users and a source.
(async () => {
  const { default: assert } = await import("node:assert/strict");
  const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ? `${process.env.PLAYWRIGHT_MODULE}/index.mjs` : "playwright");
  const base = process.env.VERIFY_BASE_URL || "http://127.0.0.1:3011";
  const api = process.env.AUTH_TEST_API || "http://127.0.0.1:3002/v1";
  assert(process.env.AUTH_TEST_ISOLATED === "true" && new URL(api).port === "3002", "Use an isolated test API on port 3002; never point this test at user data.");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const email = `auth-${Date.now()}@example.test`;
  const password = "test-only-password-73!";
  const errors = [];
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    for (const endpoint of ["collections", "datasets", "sources", "runs/11111111-1111-4111-8111-111111111111/events"]) {
      assert.equal((await context.request.get(`${api}/${endpoint}`)).status(), 401);
    }
    assert.equal((await context.request.get(`${base}/api/v1/datasets`)).status(), 401);
    assert.equal((await context.request.get(`${base}/api/v1/internal/search`)).status(), 404);
    assert.equal((await context.request.post(`${base}/api/v1/auth/login`, { headers: { Origin: "https://untrusted.example" }, data: { email, password } })).status(), 403);

    await page.goto(`${base}/collections?query=robotics`);
    await page.waitForURL(/\/login\?next=/);
    await page.getByRole("heading", { name: "Sign in to Datavault" }).waitFor();
    assert.equal(await page.getByRole("navigation", { name: "Workspace" }).count(), 0);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByText("Enter your email address.", { exact: true }).waitFor();
    await page.waitForFunction(() => document.activeElement.id === "email");
    await page.screenshot({ path: "/tmp/datavault-auth-desktop.png", fullPage: true });

    await page.getByRole("link", { name: "Create an account", exact: true }).click();
    await page.getByLabel("Full name", { exact: true }).fill("Auth Test Researcher");
    await page.getByLabel("Email address", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm password", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await page.getByText("Passwords don’t match.", { exact: true }).waitFor();
    await page.getByLabel("Confirm password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Show password" }).click();
    assert.equal(await page.getByLabel("Password", { exact: true }).getAttribute("type"), "text");
    await page.getByRole("button", { name: "Hide password" }).click();
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await page.waitForURL(`${base}/collections?query=robotics`, { timeout: 20000 });
    await page.getByRole("button", { name: "Account menu for Auth Test Researcher" }).waitFor();
    const cookie = (await context.cookies()).find((item) => item.name === "dv_session");
    assert(cookie && cookie.httpOnly && cookie.sameSite === "Lax");
    assert(!(await page.evaluate(() => document.cookie)).includes("dv_session"));
    assert.equal(await page.evaluate(() => localStorage.getItem("dv_token")), null);
    assert.equal((await context.request.get(`${base}/api/v1/collections`)).status(), 200);

    const sourceResponse = await context.request.post(`${base}/api/v1/sources`, { headers: { Origin: base }, data: { domain: "auth-fixture.example.test" } });
    assert.equal(sourceResponse.status(), 201);
    const source = await sourceResponse.json();
    const second = await context.request.post(`${api}/auth/register`, { data: { email: `second-${email}`, password, name: "Second fixture" } });
    assert.equal(second.status(), 201);
    const secondUser = await second.json();
    const secondHeaders = { Authorization: `Bearer ${secondUser.token}` };
    assert.equal((await context.request.get(`${api}/sources`, { headers: secondHeaders }).then((res) => res.json())).data.length, 0);
    assert.equal((await context.request.patch(`${api}/sources/${source.id}`, { headers: secondHeaders, data: { enabled: false } })).status(), 404);
    const otherDevice = await context.request.post(`${api}/auth/login`, { data: { email, password } }).then((res) => res.json());
    assert(otherDevice.token !== cookie.value, "Separate logins must have distinct session IDs");

    const otherTab = await context.newPage();
    await otherTab.goto(`${base}/datasets`);
    await otherTab.getByRole("button", { name: "Account menu for Auth Test Researcher" }).waitFor();
    const account = page.getByRole("button", { name: "Account menu for Auth Test Researcher" });
    await account.focus(); await page.keyboard.press("ArrowDown");
    await page.getByRole("menuitem", { name: "Account settings" }).waitFor();
    assert.equal(await page.getByRole("menuitem", { name: "Account settings" }).evaluate((el) => el === document.activeElement), true);
    await page.keyboard.press("Escape");
    assert.equal(await account.evaluate((el) => el === document.activeElement), true);
    await account.click();
    await page.route(`${base}/api/v1/auth/logout`, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "Simulated outage" }) }));
    await page.getByRole("menuitem", { name: "Log out", exact: true }).click();
    await page.getByRole("menu").getByRole("alert").waitFor();
    assert((await page.getByRole("menu").getByRole("alert").innerText()).includes("Couldn’t sign out"));
    await page.unroute(`${base}/api/v1/auth/logout`);
    await page.getByRole("menuitem", { name: "Log out", exact: true }).click();
    await page.waitForURL(/\/login/);
    await page.getByText("You’ve been signed out.", { exact: true }).waitFor();
    await otherTab.waitForURL(/\/login/);
    assert(!(await context.cookies()).some((item) => item.name === "dv_session"));
    assert.equal((await context.request.get(`${api}/auth/me`, { headers: { Authorization: `Bearer ${cookie.value}` } })).status(), 401);
    assert.equal((await context.request.get(`${api}/auth/me`, { headers: { Authorization: `Bearer ${otherDevice.token}` } })).status(), 200);
    await otherTab.close();

    await page.goto(`${base}/login?next=https%3A%2F%2Funtrusted.example`);
    await page.getByLabel("Email address").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("incorrect-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.locator("main").getByRole("alert").waitFor();
    assert.equal(await page.getByLabel("Email address").inputValue(), email);
    assert.equal(await page.getByLabel("Password", { exact: true }).inputValue(), "");
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL(`${base}/`);
    await page.reload();
    await page.getByRole("button", { name: "Account menu for Auth Test Researcher" }).waitFor();

    // Revocation outside this tab must be detected before any protected data loads.
    const active = (await context.cookies()).find((item) => item.name === "dv_session");
    await context.request.post(`${api}/auth/logout`, { headers: { Authorization: `Bearer ${active.value}` } });
    await page.goto(`${base}/datasets`);
    await page.waitForURL(/\/login/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.getByRole("heading", { name: "Sign in to Datavault" }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.screenshot({ path: "/tmp/datavault-auth-mobile.png", fullPage: true });
    await page.getByRole("link", { name: "Create an account", exact: true }).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.getByRole("button", { name: "Create account", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: "/tmp/datavault-register-mobile.png", fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS: real registration/login, validation, HttpOnly sessions, safe redirects, reload, account menu keyboard access, logout revocation, multi-tab logout, independent sessions, workspace isolation, expiry, mobile and reduced motion");
  } catch (error) {
    console.error("Auth test stopped at:", page.url(), (await page.locator("main").innerText()).slice(0, 2200), errors);
    throw error;
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
