// Thin fetch helpers. Every call reports its round-trip time so the spike can judge "feels fast".
async function call(method, path, body, timeoutMs) {
  const t0 = performance.now();
  const res = await fetch(path, {
    method,
    signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
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
// docs/plans/metric-save-contract.md (DEC-020): one call for the whole page. The spike sends no calcs yet.
// body = { op_id, candidate, calcs }; resend the same op_id on Retry so a save that landed reports replayed.
export const saveMetric = body => call('POST', '/api/metrics/save', body, 30000);
