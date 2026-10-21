import { useEffect, useState } from "react";
export function focusGeography(id: string | null) {
  window.dispatchEvent(
    new CustomEvent("observatory-geography-focus", { detail: { id } }),
  );
}
export function useFocusedGeography() {
  const [id, setId] = useState<string | null>(null);
  useEffect(() => {
    const update = (event: Event) =>
      setId((event as CustomEvent<{ id: string | null }>).detail.id);
    window.addEventListener("observatory-geography-focus", update);
    return () =>
      window.removeEventListener("observatory-geography-focus", update);
  }, []);
  return id;
}
