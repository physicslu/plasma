"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "plasma-theme";

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export default function ThemeSwitch({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    const restored: Theme = saved === "dark" ? "dark" : "light";
    setTheme(restored);
    applyTheme(restored);
  }, []);

  function selectTheme(next: Theme) {
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div className={`themeSwitch ${className}`.trim()} role="group" aria-label="Theme">
      <button
        type="button"
        className={theme === "light" ? "active" : ""}
        aria-pressed={theme === "light"}
        data-theme-choice="light"
        onClick={() => selectTheme("light")}
      >
        Light
      </button>
      <button
        type="button"
        className={theme === "dark" ? "active" : ""}
        aria-pressed={theme === "dark"}
        data-theme-choice="dark"
        onClick={() => selectTheme("dark")}
      >
        Dark
      </button>
    </div>
  );
}
