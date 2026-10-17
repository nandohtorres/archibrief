import {
  ADMIN_KEY_STORAGE_KEY,
  loadAdminKey,
  saveAdminKey,
} from "../../frontend/lib/admin-key";

function memoryStore(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

describe("admin key storage", () => {
  it("keeps the key in session storage only", () => {
    const session = memoryStore();
    saveAdminKey(session, "secret");
    expect(session.data.get(ADMIN_KEY_STORAGE_KEY)).toBe("secret");
    expect(loadAdminKey(session, memoryStore())).toBe("secret");
  });

  it("forgets the key when cleared", () => {
    const session = memoryStore({ [ADMIN_KEY_STORAGE_KEY]: "secret" });
    saveAdminKey(session, "");
    expect(session.data.has(ADMIN_KEY_STORAGE_KEY)).toBe(false);
  });

  it("moves a key persisted by older builds out of local storage", () => {
    // Older builds kept the key in localStorage.
    const session = memoryStore();
    const legacy = memoryStore({ [ADMIN_KEY_STORAGE_KEY]: "old-secret" });
    expect(loadAdminKey(session, legacy)).toBe("old-secret");
    expect(legacy.data.has(ADMIN_KEY_STORAGE_KEY)).toBe(false);
    expect(session.data.get(ADMIN_KEY_STORAGE_KEY)).toBe("old-secret");
  });

  it("prefers the current session key over a legacy one", () => {
    const session = memoryStore({ [ADMIN_KEY_STORAGE_KEY]: "current" });
    const legacy = memoryStore({ [ADMIN_KEY_STORAGE_KEY]: "old" });
    expect(loadAdminKey(session, legacy)).toBe("current");
    expect(legacy.data.has(ADMIN_KEY_STORAGE_KEY)).toBe(false);
  });
});
