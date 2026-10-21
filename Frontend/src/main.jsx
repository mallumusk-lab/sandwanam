import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App.jsx";
import { applyTheme, storedTheme } from "./ui/theme.js";
import "./ui/tokens.css";
import "./ui/base.css";
import "./ui/components.css";

// Applied before the first render (and without an inline script, so the
// Content-Security-Policy can forbid them).
applyTheme(storedTheme());

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
