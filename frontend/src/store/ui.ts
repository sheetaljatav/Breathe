/**
 * Ephemeral UI state. Anything that doesn't belong on the server lives here.
 *
 * The current `orgId` is persisted to localStorage so a page refresh keeps
 * the user's selected org. It's still validated against /api/orgs/ on boot —
 * stale localStorage values fall back to the user's first membership.
 */

import { create } from "zustand";

interface UiState {
  orgId: number | null;
  setOrgId: (id: number | null) => void;
  selectedRowIds: Set<number>;
  setSelectedRowIds: (ids: Set<number>) => void;
  clearSelection: () => void;
}

const ORG_KEY = "breathe.orgId";

export const useUiStore = create<UiState>((set) => ({
  orgId: (() => {
    const raw = localStorage.getItem(ORG_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) && n > 0 ? n : null;
  })(),
  setOrgId: (id) => {
    if (id) localStorage.setItem(ORG_KEY, String(id));
    else localStorage.removeItem(ORG_KEY);
    set({ orgId: id });
  },
  selectedRowIds: new Set(),
  setSelectedRowIds: (ids) => set({ selectedRowIds: ids }),
  clearSelection: () => set({ selectedRowIds: new Set() }),
}));
