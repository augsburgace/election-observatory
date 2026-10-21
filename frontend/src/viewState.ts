import { useEffect, useState } from "react";
/** Small non-sensitive UI selections live beside the evidence query in the URL. */
export function useViewOption<T extends string>(key: string, fallback: T) {
  const name = `ui_${key}`;
  const [value, setValue] = useState<T>(
    () => (new URLSearchParams(location.search).get(name) as T) || fallback,
  );
  useEffect(() => {
    const restore = () =>
      setValue(
        (new URLSearchParams(location.search).get(name) as T) || fallback,
      );
    window.addEventListener("popstate", restore);
    window.addEventListener("observatory-layout", restore);
    return () => {
      window.removeEventListener("popstate", restore);
      window.removeEventListener("observatory-layout", restore);
    };
  }, [name, fallback]);
  function update(next: T) {
    setValue(next);
    const params = new URLSearchParams(location.search);
    params.set(name, next);
    history.replaceState(null, "", `?${params}`);
    window.dispatchEvent(new Event("observatory-layout"));
  }
  return [value, update] as const;
}
export function currentLayout() {
  return Object.fromEntries(
    [...new URLSearchParams(location.search)].filter(
      ([key]) => key.startsWith("ui_") || key === "tab",
    ),
  );
}
