// src/lib/api.js
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function pingHealth(signal) {
  const res = await fetch(`${API_URL}/health`, { signal });
  if (!res.ok) return false;
  const data = await res.json().catch(() => ({}));
  return data?.status === 'ok';
}

export function uploadFiles(files, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f.file ? f.file : f));

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}/api/upload`);
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && typeof onProgress === 'function') {
        const pct = Math.round((e.loaded / e.total) * 100);
        onProgress(pct);
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload.'));
    xhr.onload = () => {
      const ok = xhr.status >= 200 && xhr.status < 300;
      if (ok) return resolve(xhr.response);
      const message = xhr.response?.detail || `Upload failed (${xhr.status})`;
      reject(new Error(message));
    };
    xhr.send(form);
  });
}

export async function getJob(jobId) {
  const res = await fetch(`${API_URL}/api/job/${jobId}`);
  if (!res.ok) throw new Error('Job not found');
  return res.json();
}

export async function startRender(jobId, opts = {}) {
  const res = await fetch(`${API_URL}/api/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, ...opts }), // <-- send slide_seconds & xfade_seconds
  });
  if (!res.ok) throw new Error('Render start failed');
  return res.json();
}

export async function fetchRenderStatus(renderId) {
  const res = await fetch(`${API_URL}/api/render/${renderId}/status`);
  if (!res.ok) throw new Error('Render status not found');
  return res.json(); // {status, progress, download_url, error}
}
