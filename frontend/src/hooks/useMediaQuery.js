import { useSyncExternalStore } from "react";

/**
 * 033: whether a CSS media query matches, kept current as the viewport
 * changes. Subscribes through matchMedia; where matchMedia is absent
 * (jsdom, an old browser) it answers false and never subscribes, so a
 * component using it renders its wide layout there.
 */
const hasMatchMedia = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function";

export default function useMediaQuery(query) {
  const subscribe = (onChange) => {
    if (!hasMatchMedia()) return () => {};
    const list = window.matchMedia(query);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  };
  const getSnapshot = () => hasMatchMedia() && window.matchMedia(query).matches;
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
