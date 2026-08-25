import { useSyncExternalStore } from "react";

const ROUTE_CHANGE_EVENT = "plasma-render-route-change";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(ROUTE_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(ROUTE_CHANGE_EVENT, onChange);
  };
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname, () => "/");
}

export function navigate(href: string): void {
  if (href !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.pushState({}, "", href);
    window.dispatchEvent(new Event(ROUTE_CHANGE_EVENT));
  }
}

export function replaceRoute(href: string): void {
  if (href !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.replaceState({}, "", href);
    window.dispatchEvent(new Event(ROUTE_CHANGE_EVENT));
  }
}
