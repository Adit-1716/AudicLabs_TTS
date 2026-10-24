const BASE = import.meta.env.VITE_API_URL || "/api";

export function getToken() {
  return localStorage.getItem("th_token") || "";
}

export function getOrg() {
  return localStorage.getItem("th_org") || "";
}

export function setSession(token, orgId) {
  if (token) localStorage.setItem("th_token", token);
  if (orgId) localStorage.setItem("th_org", orgId);
}

export function clearSession() {
  localStorage.removeItem("th_token");
  localStorage.removeItem("th_org");
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  const org = getOrg();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (org) headers["X-Org-Id"] = org;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export function download(path, filename) {
  return fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}`, "X-Org-Id": getOrg() },
  })
    .then((r) => r.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
}
