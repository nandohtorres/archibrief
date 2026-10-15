// Where the pre-shared admin key (ADR-0044) is kept in the browser.
//
// sessionStorage, not localStorage (Codex F18): the key unlocks paid
// reviews, so it should not outlive the tab or sit on disk on a shared
// machine. It survives a reload of the same tab, which is all the polling
// flow needs. A key saved by older builds in localStorage is moved over
// once and deleted from there.
export const ADMIN_KEY_STORAGE_KEY = "archibrief-admin-key";

type KeyValueStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function loadAdminKey(session: KeyValueStore, legacy: KeyValueStore): string {
  const legacyValue = legacy.getItem(ADMIN_KEY_STORAGE_KEY);
  if (legacyValue !== null) {
    legacy.removeItem(ADMIN_KEY_STORAGE_KEY);
    if (!session.getItem(ADMIN_KEY_STORAGE_KEY) && legacyValue) {
      session.setItem(ADMIN_KEY_STORAGE_KEY, legacyValue);
    }
  }
  return session.getItem(ADMIN_KEY_STORAGE_KEY) ?? "";
}

export function saveAdminKey(session: KeyValueStore, value: string): void {
  if (value) {
    session.setItem(ADMIN_KEY_STORAGE_KEY, value);
  } else {
    session.removeItem(ADMIN_KEY_STORAGE_KEY);
  }
}
