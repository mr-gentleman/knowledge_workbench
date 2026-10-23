// Thin fetch helpers. Every call reports its round-trip time so the spike can judge "feels fast".
async function call(method, path, body) {
  const t0 = performance.now();
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const ms = Math.round(performance.now() - t0);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || res.statusText), { status: res.status, ms });
  return { data, ms };
}

export const getMe = () => call('GET', '/api/me');
export const listCandidates = () => call('GET', '/api/candidates');
export const getCandidate = id => call('GET', `/api/candidates/${id}`);
export const saveCandidate = (id, expected_revision, fields) =>
  call('PUT', `/api/candidates/${id}`, { expected_revision, fields });
