"use client";

import { useEffect, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "plasma-theme";
const THEME_CHANGE_EVENT = "plasma-theme-change";

function readTheme(): Theme {
  return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
}

function subscribeTheme(onStoreChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY) onStoreChange();
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(THEME_CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(THEME_CHANGE_EVENT, onStoreChange);
  };
}

function subscribeHydration(): () => void {
  return () => {};
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export default function ThemeSwitch({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => "light");
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function selectTheme(next: Theme) {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
    applyTheme(next);
    window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
  }

  return (
    <div
      className={`themeSwitch ${className}`.trim()}
      role="group"
      aria-label="Theme"
      aria-busy={!hydrated}
    >
      <button
        type="button"
        disabled={!hydrated}
        className={theme === "light" ? "active" : ""}
        aria-pressed={theme === "light"}
        data-theme-choice="light"
        onClick={() => selectTheme("light")}
      >
        Light
      </button>
      <button
        type="button"
        disabled={!hydrated}
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
