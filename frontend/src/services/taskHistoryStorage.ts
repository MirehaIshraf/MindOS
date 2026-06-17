export const recentTasksStorageKey = "mindos.tasks.recent";

export function loadRecentTaskHistory<T>(): T[] {
  try {
    const raw = localStorage.getItem(recentTasksStorageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveRecentTaskHistory<T>(tasks: T[]) {
  localStorage.setItem(recentTasksStorageKey, JSON.stringify(tasks.slice(0, 20)));
}

export function clearRecentTaskHistoryStorage() {
  localStorage.removeItem(recentTasksStorageKey);
}
