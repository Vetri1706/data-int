/** Never allow auth callbacks to navigate off-site or back into authentication. */
export function safeReturnPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return "/";
  try {
    const url = new URL(value, "http://datavault.local");
    if (url.origin !== "http://datavault.local" || /^\/(login|register|api)(\/|$)/.test(url.pathname)) return "/";
    return url.pathname + url.search + url.hash;
  } catch { return "/"; }
}
