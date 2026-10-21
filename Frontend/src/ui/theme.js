// Theme preference: "system" (default), "light" or "dark". Applied from JavaScript so the
// Content-Security-Policy can forbid inline scripts.
const KEY = "theme";
const VALUES = new Set(["system", "light", "dark"]);

export function storedTheme() {
  try {
    const value = localStorage.getItem(KEY);
    return VALUES.has(value) ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(value) {
  const theme = VALUES.has(value) ? value : "system";
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Storage can be unavailable (private mode); the choice still applies to this page.
  }
  return theme;
}
