// frontend/src/lib/api.js
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function pingHealth(signal) {
  const res = await fetch(`${API_URL}/health`, { signal });
  if (!res.ok) return false;
  const data = await res.json().catch(() => ({}));
  return data?.status === 'ok';
}
