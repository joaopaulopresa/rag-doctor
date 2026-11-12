import { useEffect, useState } from "react";
import { api } from "./api";
import type { Catalog } from "./types";

let cached: Catalog | null = null;

export function useCatalog(): Catalog | null {
  const [catalog, setCatalog] = useState<Catalog | null>(cached);
  useEffect(() => {
    if (!cached) api<Catalog>("/api/admin/catalog").then((c) => setCatalog((cached = c)));
  }, []);
  return catalog;
}
