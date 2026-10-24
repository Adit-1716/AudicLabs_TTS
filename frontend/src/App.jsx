import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { api, clearSession, download, getOrg, getToken, setSession } from "./api";

const DEMO_ACCOUNTS = [
  { role: "Owner", email: "admin@acme.local", label: "👑 Owner (Asha Patel)" },
  { role: "Project Manager", email: "pm@acme.local", label: "📂 Project Manager (Rohit Sharma)" },
  { role: "Transcriber", email: "transcriber@acme.local", label: "✍️ Transcriber (Meera Iyer)" },
  { role: "Reviewer", email: "reviewer@acme.local", label: "🔍 Reviewer (Kabir Khan)" },
  { role: "Client", email: "client@acme.local", label: "👤 Client (Neha Client)" },
  { role: "Billing Manager", email: "billing@acme.local", label: "💼 Billing (Arjun Billing)" },
];

function useUser() {
  const [user, setUser] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api("/auth/me")
      .then((u) => {
        setUser(u);
        if (u.organization_id) setSession(undefined, u.organization_id);
      })
      .catch(() => setUser(false));
  }, []);
  return { user, setUser, err, setErr };
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Auth mode="login" />} />
      <Route path="/register" element={<Auth mode="register" />} />
      <Route path="/share/:token" element={<PublicShare />} />
      <Route path="/invite/:token" element={<InviteAccept />} />
      <Route path="/*" element={<Shell />} />
    </Routes>
  );
}

function Auth({ mode }) {
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", organization_name: "Acme Media", totp: "" });
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body =
        mode === "login"
          ? { email: form.email, password: form.password, totp: form.totp || null }
          : form;
      const data = await api(path, { method: "POST", body: JSON.stringify(body) });
      setSession(data.token, data.user.organization_id);
      nav("/");
    } catch (ex) {
      setError(ex.message);
    }
  }
  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <h1>Transcribe Hub</h1>
        <p className="muted">Multi-tenant transcription studio for lectures, interviews and podcasts.</p>
        {mode === "register" && (
          <>
            <label>Full name<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
            <label>Organization<input value={form.organization_name} onChange={(e) => setForm({ ...form, organization_name: e.target.value })} /></label>
          </>
        )}
        <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {mode === "login" && <label>2FA code (if enabled)<input value={form.totp} onChange={(e) => setForm({ ...form, totp: e.target.value })} /></label>}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button type="submit">{mode === "login" ? "Sign in" : "Create workspace"}</button>
          <button type="button" className="ghost" onClick={() => nav(mode === "login" ? "/register" : "/login")}>
            {mode === "login" ? "Need an account" : "Have an account"}
          </button>
        </div>
        <p className="muted">Demo: admin@acme.local / DemoPass123!</p>
      </form>
    </div>
  );
}

function Shell() {
  const { user, setUser } = useUser();
  const nav = useNavigate();
  if (user === null) return <div className="main">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  const links = [
    ["/", "Overview"],
    ["/projects", "Projects"],
    ["/upload", "Upload & Samples"],
    ["/transcripts", "Transcripts"],
    ["/reviews", "Review & QA"],
    ["/client", "Client portal"],
    ["/billing", "Billing"],
    ["/reports", "Reports"],
    ["/workflow", "Workflow"],
    ["/integrations", "Integrations"],
    ["/users", "People"],
    ["/notifications", "Alerts"],
    ["/audit", "Audit"],
    ["/settings", "Settings"],
  ];
  return (
    <div className="shell">
      <aside className="nav">
        <div className="brand">Transcribe Hub</div>
        {links.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"}>
            {label}
          </NavLink>
        ))}
        <div className="meta">
          <div style={{ fontWeight: 600, color: "#fff" }}>{user.full_name}</div>
          <div style={{ margin: "4px 0" }}>
            <span className={`role-badge role-${(user.assessment_role || "editor").toLowerCase()}`}>
              {user.assessment_role || user.role}
            </span>
            <span style={{ marginLeft: 6, fontSize: "0.75rem", opacity: 0.8 }}>({user.role})</span>
          </div>

          {/* Quick RBAC Role Switcher */}
          <div className="role-switcher-box">
            <label>⚡ Fast RBAC Role Switcher</label>
            <select
              value={user.email}
              onChange={async (e) => {
                const found = DEMO_ACCOUNTS.find((a) => a.email === e.target.value);
                if (found) {
                  try {
                    const data = await api("/auth/login", {
                      method: "POST",
                      body: JSON.stringify({ email: found.email, password: "DemoPass123!" }),
                    });
                    setSession(data.token, data.user.organization_id);
                    window.location.reload();
                  } catch (err) {
                    alert(err.message);
                  }
                }
              }}
            >
              {DEMO_ACCOUNTS.map((a) => (
                <option key={a.email} value={a.email}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>

          <button
            className="link"
            onClick={async () => {
              await api("/auth/logout", { method: "POST" }).catch(() => {});
              clearSession();
              setUser(false);
              nav("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard user={user} />} />
          <Route path="/projects" element={<Projects user={user} />} />
          <Route path="/projects/:id" element={<ProjectDetail user={user} />} />
          <Route path="/projects/:id/editor/:tid" element={<Editor user={user} />} />
          <Route path="/upload" element={<UploadPage user={user} />} />
          <Route path="/transcripts" element={<Transcripts user={user} />} />
          <Route path="/reviews" element={<Reviews user={user} />} />
          <Route path="/client" element={<ClientPortal user={user} />} />
          <Route path="/billing" element={<Billing user={user} />} />
          <Route path="/reports" element={<Reports user={user} />} />
          <Route path="/workflow" element={<Workflow user={user} />} />
          <Route path="/integrations" element={<Integrations user={user} />} />
          <Route path="/users" element={<People user={user} />} />
          <Route path="/notifications" element={<Alerts user={user} />} />
          <Route path="/audit" element={<Audit user={user} />} />
          <Route path="/settings" element={<Settings user={user} />} />
          <Route path="/search" element={<SearchPage user={user} />} />
        </Routes>
      </main>
    </div>
  );
}

function Dashboard() {
  const [kpis, setKpis] = useState(null);
  const [usage, setUsage] = useState(null);
  const [q, setQ] = useState("");
  const nav = useNavigate();
  useEffect(() => {
    api("/reports/kpis").then(setKpis).catch(() => setKpis({}));
    api("/usage").then(setUsage).catch(() => setUsage(null));
  }, []);
  return (
    <div>
      <div className="top">
        <div>
          <h1>Studio overview</h1>
          <p className="muted">Credits, delivery and work in flight for this workspace.</p>
        </div>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            nav(`/search?q=${encodeURIComponent(q)}`);
          }}
        >
          <input placeholder="Search projects, people, transcripts" value={q} onChange={(e) => setQ(e.target.value)} />
          <button>Search</button>
        </form>
      </div>
      <div className="grid kpis">
        {kpis &&
          Object.entries({
            "Total projects": kpis.total_projects,
            "Pending reviews": kpis.pending_reviews,
            Completed: kpis.completed_projects,
            Revenue: kpis.revenue,
            "Avg accuracy": kpis.average_accuracy,
            "Avg hours": kpis.average_delivery_hours,
            "Credits used": kpis.credits_used,
          }).map(([k, v]) => (
            <div className="card kpi" key={k}>
              <span className="muted">{k}</span>
              <b>{v ?? "—"}</b>
            </div>
          ))}
      </div>
      {usage && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>This month’s AudicLabs credits</h3>
          <p>
            {usage.used} / {usage.quota} used · {usage.remaining} remaining
          </p>
          <table>
            <thead>
              <tr>
                <th>Member</th>
                <th>Credits</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(usage.by_member || {}).map(([n, c]) => (
                <tr key={n}>
                  <td>{n}</td>
                  <td>{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Projects() {
  const [rows, setRows] = useState([]);
  const [title, setTitle] = useState("New lecture");
  const nav = useNavigate();
  const load = () => api("/projects").then(setRows);
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <div className="top">
        <h1>Projects</h1>
        <form
          className="row"
          onSubmit={async (e) => {
            e.preventDefault();
            const p = await api("/projects", { method: "POST", body: JSON.stringify({ title }) });
            nav(`/projects/${p.id}`);
          }}
        >
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
          <button>Create</button>
        </form>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Progress</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} onClick={() => nav(`/projects/${p.id}`)} style={{ cursor: "pointer" }}>
                <td>{p.title}</td>
                <td>
                  <span className="badge">{p.status}</span>
                </td>
                <td>{p.priority}</td>
                <td>{p.progress_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProjectDetail({ user }) {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [members, setMembers] = useState([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [denoiseMode, setDenoiseMode] = useState({});
  const nav = useNavigate();

  const load = () =>
    Promise.all([api(`/projects/${id}`), api("/orgs/members")])
      .then(([a, b]) => {
        setP(a);
        setMembers(b);
      })
      .catch((e) => setErr(e.message));

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [id]);

  if (!p) return <p>{err || "Loading…"}</p>;

  const role = user?.role || "CLIENT";
  const isClient = role === "CLIENT";
  const isTranscriber = role === "TRANSCRIBER";
  const isReviewer = role === "REVIEWER";
  const isOwnerOrPM = ["ORG_ADMIN", "PROJECT_MANAGER", "SUPER_ADMIN"].includes(role);

  async function updateStatus(newStatus, note = "") {
    try {
      await api(`/projects/${id}/status`, { method: "POST", body: JSON.stringify({ status: newStatus, note }) });
      setMsg(`Status updated to ${newStatus}`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleAutoAssign() {
    setMsg("Auto-assigning team members based on RBAC roles…");
    try {
      await api(`/projects/${id}/auto-assign`, { method: "POST" });
      setMsg("Successfully auto-assigned transcriber and reviewer!");
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div>
      <div className="top">
        <div>
          <h1>{p.title}</h1>
          <p className="muted">
            {p.category} · Priority: {p.priority} · Language: {p.language} · Deadline: {p.deadline || "none"}
          </p>
        </div>
        <div className="row">
          <span className={`badge ${p.status.toLowerCase().replace(/ /g, "_")}`}>{p.status}</span>
          {isOwnerOrPM && (
            <select
              value={p.status}
              onChange={(e) => updateStatus(e.target.value)}
              style={{ width: "auto" }}
            >
              {["Draft", "Assigned", "In Progress", "Under Review", "Revision Requested", "Approved", "Delivered", "Archived"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Role Banner */}
      <div className={`role-banner ${isClient ? "viewer" : isOwnerOrPM ? "owner" : "editor"}`}>
        <div>
          <b>Role: {user?.full_name} ({user?.assessment_role} · {user?.role})</b>
          <div style={{ fontSize: "0.82rem", opacity: 0.9 }}>
            {isClient && "Client Mode: You can play media audio sound, request revisions, and view transcripts."}
            {isTranscriber && "Transcriber Mode: You can edit transcripts, insert timestamps, play audio, and submit for review."}
            {isReviewer && "Reviewer QA Mode: You can verify audio sound, review transcripts, approve, or request revisions."}
            {isOwnerOrPM && "Manager/Owner Mode: Full control to auto-assign, change status, run speech AI pipeline, and manage media."}
          </div>
        </div>
        <div className="row">
          {/* Quick task action buttons based on role */}
          {isOwnerOrPM && (
            <button className="btn-task" onClick={handleAutoAssign}>
              ⚡ Auto-Assign Team
            </button>
          )}
          {isTranscriber && p.status === "In Progress" && (
            <button className="btn-task" onClick={() => updateStatus("Under Review", "Transcriber finished work")}>
              📋 Submit for Review
            </button>
          )}
          {(isReviewer || isOwnerOrPM) && p.status === "Under Review" && (
            <>
              <button className="btn-task" style={{ background: "var(--good)" }} onClick={() => updateStatus("Approved", "QA Approved")}>
                ✅ Approve Project
              </button>
              <button className="btn-task" style={{ background: "var(--bad)" }} onClick={() => updateStatus("Revision Requested", "QA Requested Changes")}>
                🔄 Request Revision
              </button>
            </>
          )}
          {isClient && (
            <button className="btn-task ghost" onClick={() => updateStatus("Revision Requested", "Client requested changes")}>
              🔄 Request Revision
            </button>
          )}
          {isOwnerOrPM && p.status === "Approved" && (
            <button className="btn-task" style={{ background: "var(--good)" }} onClick={() => updateStatus("Delivered", "Project finalized and delivered")}>
              🚀 Mark Delivered
            </button>
          )}
        </div>
      </div>

      {err && <p className="error">{err}</p>}
      {msg && <p className="ok">{msg}</p>}

      <div className="grid" style={{ gridTemplateColumns: "1.1fr 0.9fr" }}>
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
            <h3>Project Audio & Media</h3>
            <span className="muted">{p.media.length} file(s) attached</span>
          </div>

          {p.media.map((m) => {
            const token = getToken();
            const isDenoised = denoiseMode[m.id];
            const audioUrl = isDenoised
              ? `/api/media/${m.id}/stream-denoised?token=${token}`
              : `/api/media/${m.id}/stream?token=${token}`;

            return (
              <div
                key={m.id}
                style={{
                  background: "#fff",
                  border: "1px solid var(--line)",
                  borderRadius: 12,
                  padding: 14,
                  marginBottom: 12,
                }}
              >
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <div>
                    <b>{m.original_name}</b>{" "}
                    <span className={`badge ${m.job_status}`}>{m.job_status}</span>
                  </div>
                  <span className="muted" style={{ fontSize: "0.8rem" }}>
                    {(m.size_bytes / (1024 * 1024)).toFixed(2)} MB · {m.content_type}
                  </span>
                </div>

                {/* Sound playback audio player */}
                <div style={{ marginTop: 8 }}>
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                      🔊 Sound Player: {isDenoised ? "AI Cleaned / Denoised Audio" : "Original Audio"}
                    </span>
                    <button
                      className="ghost"
                      style={{ fontSize: "0.72rem", padding: "2px 8px" }}
                      onClick={() => setDenoiseMode({ ...denoiseMode, [m.id]: !isDenoised })}
                    >
                      Switch to {isDenoised ? "Original Audio" : "Cleaned Audio"}
                    </button>
                  </div>
                  <audio
                    controls
                    src={audioUrl}
                    style={{ width: "100%", height: 36 }}
                    preload="metadata"
                  />
                </div>

                {m.job_error && <div className="error" style={{ marginTop: 6 }}>{m.job_error}</div>}

                <div className="row" style={{ marginTop: 10, justifyContent: "flex-end" }}>
                  {(m.job_status === "failed" || isOwnerOrPM) && (
                    <button
                      className="ghost btn-task"
                      onClick={() => api(`/media/${m.id}/retry`, { method: "POST" }).then(load)}
                    >
                      🔄 Re-run Speech AI
                    </button>
                  )}
                </div>
              </div>
            );
          })}

          <h4 style={{ marginTop: 18, marginBottom: 8 }}>Add Audio Media or Dataset</h4>
          <Uploader projectId={id} onDone={load} user={user} />
        </div>

        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <h3>Team & Workflow Timeline</h3>
            {isOwnerOrPM && (
              <button className="ghost btn-task" style={{ fontSize: "0.78rem" }} onClick={handleAutoAssign}>
                ⚡ Auto-Assign
              </button>
            )}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label>Assigned Members:</label>
            {(p.assignments || []).length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem" }}>No team members assigned yet.</p>
            ) : (
              <div className="row" style={{ gap: 6, marginBottom: 10 }}>
                {p.assignments.map((a) => {
                  const m = members.find((x) => x.id === a.user_id);
                  return (
                    <span key={a.id} className="badge" style={{ background: "#e8effc", color: "#1e40af" }}>
                      👤 {m?.full_name || a.user_id} ({a.role_on_project})
                    </span>
                  );
                })}
              </div>
            )}

            {isOwnerOrPM && (
              <select
                onChange={async (e) => {
                  if (!e.target.value) return;
                  await api(`/projects/${id}/assign`, { method: "POST", body: JSON.stringify({ user_id: e.target.value }) });
                  load();
                }}
              >
                <option value="">Manual Assign Member…</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name} ({m.role})
                  </option>
                ))}
              </select>
            )}
          </div>

          <h4 style={{ marginBottom: 6 }}>Workflow History</h4>
          <ul style={{ paddingLeft: 18, fontSize: "0.85rem", color: "var(--muted)" }}>
            {(p.timeline || []).map((h, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <b>{h.from_status || "Created"} → {h.to_status}</b>
                {h.note && ` · ${h.note}`}
                <span style={{ fontSize: "0.75rem", display: "block", color: "#9ca3af" }}>
                  {h.created_at ? new Date(h.created_at).toLocaleTimeString() : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <TranscriptJump projectId={id} user={user} />
    </div>
  );
}

function TranscriptJump({ projectId, user }) {
  const [rows, setRows] = useState([]);
  const nav = useNavigate();
  useEffect(() => {
    api("/transcripts").then((all) => setRows(all.filter((t) => t.project_id === projectId)));
  }, [projectId]);
  if (!rows.length) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h3>Generated Transcripts ({rows.length})</h3>
        <span className="muted">Live speech AI transcripts with sound player & editor</span>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        {rows.map((t) => {
          const token = getToken();
          const playSrc = t.play_url ? (t.play_url.includes("?") ? `${t.play_url}&token=${token}` : `${t.play_url}?token=${token}`) : "";
          return (
            <div key={t.id} className="card" style={{ background: "#fff", border: "1px solid var(--line)" }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                <b>{t.media_name || "Transcript"}</b>
                <span className="badge done">v{t.current_version} · {(t.avg_confidence * 100).toFixed(0)}% AI Conf</span>
              </div>
              {/* Quick sound player */}
              <audio
                controls
                src={playSrc}
                style={{ width: "100%", height: 32, margin: "6px 0" }}
                preload="none"
              />
              <p style={{ fontSize: "0.84rem", color: "var(--muted)", margin: "6px 0 12px", minHeight: 38 }}>
                {(t.raw_text || "").slice(0, 110)}…
              </p>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                  Language: {t.detected_language}
                </span>
                <button className="btn-task" onClick={() => nav(`/projects/${projectId}/editor/${t.id}`)}>
                  ✏️ Open Editor
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Uploader({ projectId, onDone, user }) {
  const [drag, setDrag] = useState(false);
  const [language, setLanguage] = useState("auto");
  const [hints, setHints] = useState("");
  const [denoise, setDenoise] = useState(true);
  const [diarize, setDiarize] = useState(true);
  const [autoTranscribe, setAutoTranscribe] = useState(true);
  const [langs, setLangs] = useState([]);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [previewFiles, setPreviewFiles] = useState([]);
  const [samples, setSamples] = useState([]);

  useEffect(() => {
    api("/lookups/languages")
      .then((d) => setLangs(d.languages || []))
      .catch(() => {});
    api("/samples")
      .then(setSamples)
      .catch(() => {});
  }, []);

  function handleFileSelect(files) {
    const list = [...files];
    const previewList = list.map((f) => ({
      file: f,
      name: f.name,
      sizeFormatted: `${(f.size / (1024 * 1024)).toFixed(2)} MB`,
      type: f.type || "audio/media",
      url: URL.createObjectURL(f),
    }));
    setPreviewFiles(previewList);
  }

  async function send(filesToSend) {
    const target = filesToSend || previewFiles.map((p) => p.file);
    if (!target || !target.length) return;
    setError("");
    setUploading(true);
    const fd = new FormData();
    target.forEach((f) => fd.append("files", f));
    fd.append("language", language);
    fd.append("spelling_hints", hints);
    fd.append("denoise", denoise);
    fd.append("diarize", diarize);
    try {
      await api(`/projects/${projectId}/uploads`, { method: "POST", body: fd });
      setPreviewFiles([]);
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function useDatasetSample(sampleId) {
    setError("");
    setUploading(true);
    try {
      await api(`/projects/${projectId}/use-sample`, {
        method: "POST",
        body: JSON.stringify({
          sample_id: sampleId,
          denoise,
          diarize,
          language,
          spelling_hints: hints,
        }),
      });
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div
        className="drop"
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFileSelect(e.dataTransfer.files);
        }}
      >
        <p style={{ fontWeight: 600, fontSize: "1rem", margin: "0 0 6px" }}>
          {drag ? "Drop audio/video file here" : "Drag audio/video file here or choose file"}
        </p>
        <p className="muted" style={{ fontSize: "0.82rem", margin: "0 0 12px" }}>
          Supports MP3, WAV, MP4, AVI, MKV, AAC, FLAC, M4A, OGG, WEBM
        </p>
        <input
          type="file"
          multiple
          accept=".mp3,.wav,.mp4,.avi,.mkv,.aac,.flac,.m4a,.ogg,.webm"
          onChange={(e) => handleFileSelect(e.target.files)}
        />
      </div>

      {/* Instant Sound Playback Preview of Passed Audio Files */}
      {previewFiles.length > 0 && (
        <div className="audio-preview-box">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>🔊 Sound Preview: Play & Verify Audio Before / While Transcribing</b>
            <span className="badge done">{previewFiles.length} file(s) selected</span>
          </div>
          {previewFiles.map((p, idx) => (
            <div key={idx} style={{ marginTop: 8 }}>
              <div className="row" style={{ justifyContent: "space-between", fontSize: "0.85rem" }}>
                <span>📁 <b>{p.name}</b> ({p.sizeFormatted})</span>
                <span className="muted">{p.type}</span>
              </div>
              <audio controls src={p.url} style={{ width: "100%", height: 38, marginTop: 6 }} />
            </div>
          ))}
          <div className="row" style={{ marginTop: 12, justifyContent: "space-between" }}>
            <button className="ghost" onClick={() => setPreviewFiles([])}>
              ✕ Cancel
            </button>
            <button
              className="btn-task"
              disabled={uploading}
              onClick={() => send()}
            >
              {uploading ? "Transcribing…" : "⚡ Run Auto-Transcription on Audio File"}
            </button>
          </div>
        </div>
      )}

      {/* Auto Features Config */}
      <div className="card" style={{ marginTop: 12, background: "#fbf8f2" }}>
        <h4 style={{ margin: "0 0 8px" }}>⚙️ Auto Features & AI Pipeline Configuration</h4>
        <div className="row" style={{ gap: 16 }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: 0, cursor: "pointer" }}>
            <input type="checkbox" checked={denoise} onChange={(e) => setDenoise(e.target.checked)} />
            <b>Auto Noise Reduction</b> (AudicLabs NS)
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: 0, cursor: "pointer" }}>
            <input type="checkbox" checked={diarize} onChange={(e) => setDiarize(e.target.checked)} />
            <b>Auto Speaker Diarization</b> (Speaker 1, 2…)
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: 0, cursor: "pointer" }}>
            <input type="checkbox" checked={autoTranscribe} onChange={(e) => setAutoTranscribe(e.target.checked)} />
            <b>Auto Transcribe on Upload</b>
          </label>
        </div>

        <div className="row" style={{ marginTop: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={{ marginBottom: 4 }}>Auto-Detect or Select Language</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="auto">Auto-detect Language</option>
              {(Array.isArray(langs) ? langs : []).map((l) => {
                const code = typeof l === "string" ? l : l.code || l.id || l.language;
                const name = typeof l === "string" ? l : l.name || code;
                return (
                  <option key={code} value={code}>
                    {name}
                  </option>
                );
              })}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ marginBottom: 4 }}>Spelling & Terminology Hints</label>
            <input
              value={hints}
              onChange={(e) => setHints(e.target.value)}
              placeholder="Names, brands, technical jargon"
            />
          </div>
        </div>
      </div>

      {/* Preloaded Sample Audio Datasets & Demo Sound */}
      {samples.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
            <h4 style={{ margin: 0 }}>🎧 Sample Audio Datasets (Play Sound & Transcribe)</h4>
            <span className="muted" style={{ fontSize: "0.8rem" }}>Instant 1-Click Verification</span>
          </div>
          <div className="sample-grid">
            {samples.map((s) => (
              <div className="sample-card" key={s.id}>
                <div className="sample-meta">
                  <span className="badge">{s.category}</span>
                  <b>{s.format} · {s.duration_est}</b>
                </div>
                <b style={{ fontSize: "0.92rem" }}>{s.name}</b>
                <p style={{ fontSize: "0.8rem", color: "var(--muted)", margin: "2px 0 6px" }}>
                  {s.description}
                </p>
                {/* Embedded HTML5 sound player so user can play sound immediately */}
                <audio controls src={s.stream_url} preload="none" />
                <button
                  className="btn-task"
                  style={{ marginTop: 6 }}
                  disabled={uploading}
                  onClick={() => useDatasetSample(s.id)}
                >
                  ⚡ Transcribe This Dataset
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <p className="error" style={{ marginTop: 10 }}>{error}</p>}
    </div>
  );
}

function UploadPage({ user }) {
  const [projects, setProjects] = useState([]);
  const [id, setId] = useState("");
  const [samples, setSamples] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    api("/projects").then((rows) => {
      setProjects(rows);
      if (rows[0]) setId(rows[0].id);
    });
    api("/samples").then(setSamples).catch(() => {});
  }, []);

  async function createFromSample(sample) {
    setBusy(true);
    setMsg(`Creating project and processing ${sample.name}…`);
    try {
      const res = await api("/projects/from-sample", {
        method: "POST",
        body: JSON.stringify({
          title: `Project: ${sample.name}`,
          sample_id: sample.id,
          denoise: true,
          diarize: true,
          language: "auto",
        }),
      });
      if (res.transcript_id) {
        nav(`/projects/${res.project_id}/editor/${res.transcript_id}`);
      } else {
        nav(`/projects/${res.project_id}`);
      }
    } catch (e) {
      setMsg("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="top">
        <div>
          <h1>Audio & Dataset Transcription Studio</h1>
          <p className="muted">
            Upload custom audio files, play sound previews, or launch instant transcription from benchmark datasets.
          </p>
        </div>
      </div>

      {busy && <div className="card" style={{ background: "#fef3c7", marginBottom: 16 }}>⏳ {msg}</div>}

      {/* One click fast track sample datasets */}
      {samples.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <h3>🎧 Instant Demo Datasets (Play Sound & Transcribe)</h3>
            <span className="badge done">Preloaded Benchmark Files</span>
          </div>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
            Listen to any dataset below and click "Transcribe & Open Editor" to create a fresh project with automated diarization and denoising:
          </p>
          <div className="sample-grid">
            {samples.map((s) => (
              <div className="sample-card" key={s.id}>
                <div className="sample-meta">
                  <span className="badge done">{s.format}</span>
                  <span>{s.size_formatted} · {s.duration_est}</span>
                </div>
                <b>{s.name}</b>
                <p style={{ fontSize: "0.8rem", color: "var(--muted)", margin: "4px 0" }}>
                  {s.description}
                </p>
                {/* Audio player for instant sound playback */}
                <audio controls src={s.stream_url} preload="none" />
                <button
                  className="btn-task"
                  style={{ marginTop: 8 }}
                  disabled={busy}
                  onClick={() => createFromSample(s)}
                >
                  🚀 Transcribe & Open Editor
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Target Project Upload */}
      <div className="card">
        <h3>Upload Audio to Existing Project</h3>
        {projects.length > 0 ? (
          <>
            <label style={{ marginBottom: 12 }}>
              Choose Target Project:
              <select value={id} onChange={(e) => setId(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} ({p.status})
                  </option>
                ))}
              </select>
            </label>
            {id && <Uploader projectId={id} user={user} onDone={() => nav(`/projects/${id}`)} />}
          </>
        ) : (
          <p className="muted">No projects found. Use a dataset above or create a project first.</p>
        )}
      </div>
    </div>
  );
}

function Transcripts({ user }) {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const load = () => api(`/transcripts${q ? `?q=${encodeURIComponent(q)}` : ""}`).then(setRows);
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <div className="top">
        <div>
          <h1>Transcript Repository</h1>
          <p className="muted">All speech AI generated transcripts with sound players and instant editing</p>
        </div>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Full-text search transcripts…" />
          <button>Search</button>
        </form>
      </div>
      {rows.map((t) => {
        const token = getToken();
        const playSrc = t.play_url ? (t.play_url.includes("?") ? `${t.play_url}&token=${token}` : `${t.play_url}?token=${token}`) : "";
        return (
          <div className="card" key={t.id} style={{ marginBottom: 12 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <b style={{ fontSize: "1.05rem" }}>{t.project_title}</b>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  {t.media_name} · {t.detected_language} · {(t.avg_confidence * 100).toFixed(0)}% AI Confidence · v{t.current_version}
                </div>
              </div>
              <div className="row">
                <button
                  className="btn-task ghost"
                  onClick={() => download(`/transcripts/${t.id}/export.txt`, "transcript.txt")}
                >
                  📥 TXT
                </button>
                <button
                  className="btn-task ghost"
                  onClick={() => download(`/transcripts/${t.id}/export.srt`, "transcript.srt")}
                >
                  📥 SRT
                </button>
                <button
                  className="btn-task"
                  onClick={() => nav(`/projects/${t.project_id}/editor/${t.id}`)}
                >
                  ✏️ Open Editor
                </button>
              </div>
            </div>

            {/* Quick sound player */}
            <div style={{ marginTop: 8, maxWidth: 500 }}>
              <audio
                controls
                src={playSrc}
                style={{ width: "100%", height: 32 }}
                preload="none"
              />
            </div>

            <p style={{ marginTop: 8, color: "var(--ink)" }}>{(t.raw_text || "").slice(0, 240)}…</p>
          </div>
        );
      })}
    </div>
  );
}

function Editor({ user }) {
  const { id, tid } = useParams();
  const [t, setT] = useState(null);
  const [comments, setComments] = useState([]);
  const [versions, setVersions] = useState([]);
  const [note, setNote] = useState("");
  const [speed, setSpeed] = useState(1);
  const [err, setErr] = useState("");
  const [share, setShare] = useState("");
  const [saveStatus, setSaveStatus] = useState("Saved");
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loopSegment, setLoopSegment] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [useDenoised, setUseDenoised] = useState(false);
  const [activeSegIdx, setActiveSegIdx] = useState(-1);
  const [grammarResult, setGrammarResult] = useState(null);
  const [qaScore, setQaScore] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [viewMode, setViewMode] = useState("transcript"); // 'transcript' | 'lyrics'
  const [liveLyricText, setLiveLyricText] = useState("");

  const media = useRef();
  const saveTimer = useRef();
  const segmentRefs = useRef({});

  const role = user?.role || "CLIENT";
  const isClient = role === "CLIENT";
  const isTranscriber = role === "TRANSCRIBER";
  const isReviewer = role === "REVIEWER";
  const isOwnerOrPM = ["ORG_ADMIN", "PROJECT_MANAGER", "SUPER_ADMIN"].includes(role);

  const load = () => {
    api(`/transcripts/${tid}`).then(setT);
    api(`/transcripts/${tid}/comments`).then(setComments);
    api(`/transcripts/${tid}/versions`).then(setVersions);
  };

  useEffect(() => {
    load();
  }, [tid]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.code === "Space" && e.target.tagName !== "TEXTAREA" && e.target.tagName !== "INPUT") {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isPlaying]);

  function togglePlay() {
    const el = media.current;
    if (!el) return;
    if (el.paused) {
      el.play().then(() => setIsPlaying(true)).catch(() => {});
    } else {
      el.pause();
      setIsPlaying(false);
    }
  }

  function seek(delta) {
    const el = media.current;
    if (!el) return;
    el.currentTime = Math.max(0, Math.min(el.duration || 9999, el.currentTime + delta));
  }

  function playSegment(seg) {
    const el = media.current;
    if (!el) return;
    el.currentTime = seg.start || 0;
    el.play().then(() => setIsPlaying(true)).catch(() => {});
  }

  function handleTimeUpdate(e) {
    const time = e.target.currentTime;
    setCurrentTime(time);

    if (t?.segments) {
      const idx = t.segments.findIndex(
        (s) => time >= (s.start || 0) && time <= (s.end || (s.start + 3))
      );
      if (idx !== -1 && idx !== activeSegIdx) {
        setActiveSegIdx(idx);
        if (autoScroll && segmentRefs.current[idx]) {
          segmentRefs.current[idx].scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }

      // Check loop segment
      if (loopSegment && activeSegIdx !== -1) {
        const curSeg = t.segments[activeSegIdx];
        if (curSeg && curSeg.end && time >= curSeg.end) {
          e.target.currentTime = curSeg.start || 0;
        }
      }
    }
  }

  function scheduleSave(next) {
    if (isClient) return; // Client is read-only
    setT(next);
    setSaveStatus("Saving…");
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      api(`/transcripts/${tid}`, {
        method: "PATCH",
        body: JSON.stringify({ segments: next.segments, speakers: next.speakers, note: "autosave" }),
      })
        .then(() => setSaveStatus(`Saved at ${new Date().toLocaleTimeString()}`))
        .catch((e) => {
          setSaveStatus("Error saving");
          setErr(e.message);
        });
    }, 800);
  }

  function addSegmentAfter(index) {
    if (isClient) return;
    const current = t.segments[index];
    const newStart = current ? (current.end || current.start + 2) : 0;
    const newSeg = {
      start: newStart,
      end: newStart + 3,
      speaker: current ? current.speaker : "Speaker 1",
      text: "",
      confidence: 1.0,
    };
    const nextSegs = [...t.segments.slice(0, index + 1), newSeg, ...t.segments.slice(index + 1)];
    scheduleSave({ ...t, segments: nextSegs });
  }

  function deleteSegment(index) {
    if (isClient) return;
    const nextSegs = t.segments.filter((_, i) => i !== index);
    scheduleSave({ ...t, segments: nextSegs });
  }

  async function checkGrammar() {
    setErr("");
    setStatusMsg("Checking grammar with AI…");
    try {
      const g = await api(`/transcripts/${tid}/grammar`, { method: "POST" });
      setGrammarResult(g);
      setStatusMsg(`Grammar check complete: found ${g.issues.length} suggested enhancement(s).`);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function applyGrammarFixes() {
    setErr("");
    setStatusMsg("Applying grammar fixes…");
    try {
      const updated = await api(`/transcripts/${tid}/grammar/apply`, { method: "POST" });
      setT(updated);
      setGrammarResult(null);
      setStatusMsg("Grammar enhancements applied and saved as new version!");
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function autoScoreQA() {
    setErr("");
    setStatusMsg("Calculating automated quality score…");
    try {
      const score = await api(`/transcripts/${tid}/auto-score`, { method: "POST" });
      setQaScore(score);
      setStatusMsg("Quality score generated successfully!");
    } catch (e) {
      setErr(e.message);
    }
  }

  async function setProjectStatus(newStatus, noteText) {
    try {
      await api(`/projects/${id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: newStatus, note: noteText || `Set by ${user?.full_name}` }),
      });
      setStatusMsg(`Workflow status updated to '${newStatus}'!`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  function addLyricAtCurrentTime() {
    if (isClient) return;
    const el = media.current;
    const stamp = el ? el.currentTime : currentTime;
    const textToAdd = liveLyricText.trim() || "New lyric line…";
    const newSeg = {
      start: Number(stamp.toFixed(2)),
      end: Number((stamp + 3.5).toFixed(2)),
      speaker: "Lead Vocal",
      text: textToAdd,
      confidence: 1.0,
    };
    const segs = [...(t.segments || [])];
    const insertIdx = segs.findIndex((s) => (s.start || 0) > stamp);
    if (insertIdx === -1) {
      segs.push(newSeg);
    } else {
      segs.splice(insertIdx, 0, newSeg);
    }
    setLiveLyricText("");
    scheduleSave({ ...t, segments: segs });
  }

  async function formatSongLyrics() {
    if (isClient) return;
    setStatusMsg("Formatting audio transcript into musical song lyrics…");
    try {
      const res = await api(`/transcripts/${tid}/lyrics/format`, { method: "POST" });
      setStatusMsg(`Formatted ${res.count} lines into song structure (Verses, Chorus, Outro)!`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  function exportAs(fmt) {
    const title = t?.project_title || "lyrics";
    const modeParam = viewMode === "lyrics" ? "lyrics" : "standard";
    download(`/transcripts/${tid}/export.${fmt}?mode=${modeParam}`, `${title}.${fmt}`);
  }

  if (!t) return <p>Loading editor…</p>;

  const token = getToken();
  const rawPlayUrl = t.play_url || `/api/media/${t.media_file_id}/stream`;
  const streamUrl = rawPlayUrl.includes("?") ? `${rawPlayUrl}&token=${token}` : `${rawPlayUrl}?token=${token}`;
  const denoisedStreamUrl = `/api/media/${t.media_file_id}/stream-denoised?token=${token}`;
  const audioSource = useDenoised ? denoisedStreamUrl : streamUrl;
  const isVideo = (t.media_type || "").startsWith("video");

  function fmtTime(sec) {
    const s = Math.floor(sec || 0);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m.toString().padStart(2, "0")}:${rem.toString().padStart(2, "0")}`;
  }

  return (
    <div>
      <div className="top">
        <div>
          <div className="row" style={{ gap: 8 }}>
            <h1>{t.project_title}</h1>
            <span className="badge done">v{t.current_version}</span>
            <span className="badge" style={{ background: "#e8effc", color: "#1e40af" }}>
              {t.detected_language} · {(t.avg_confidence * 100).toFixed(0)}% Conf
            </span>
          </div>
          <p className="muted" style={{ margin: "2px 0 0" }}>
            Media: {t.media_name} · Auto-save: {saveStatus}
          </p>
        </div>

        {/* View Mode Switcher: Dialogue Transcript vs Song & Audio Lyrics */}
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <div className="lyrics-view-toggle">
            <button
              className={viewMode === "transcript" ? "active" : ""}
              onClick={() => setViewMode("transcript")}
              title="Show standard speaker dialogue turns"
            >
              🎙️ Dialogue
            </button>
            <button
              className={viewMode === "lyrics" ? "active" : ""}
              onClick={() => setViewMode("lyrics")}
              title="Switch to live synchronized song lyrics and vocal player"
            >
              🎵 Song & Lyrics
            </button>
          </div>

          {/* Multi-Format File Converter: TXT, PDF, Word DOCX */}
          <div className="convert-group">
            <button className="btn-convert txt" onClick={() => exportAs("txt")} title="Convert & Download as TXT File">
              📄 TXT
            </button>
            <button className="btn-convert pdf" onClick={() => exportAs("pdf")} title="Convert & Download as PDF Document">
              📕 PDF
            </button>
            <button className="btn-convert docx" onClick={() => exportAs("docx")} title="Convert & Download as Word (DOCX) Document">
              📘 Word
            </button>
            <button className="btn-convert" onClick={() => exportAs("srt")} title="Convert to SRT Subtitles">
              🎬 SRT
            </button>
            <button
              className="btn-convert"
              onClick={async () => {
                const s = await api(`/transcripts/${tid}/share`, { method: "POST" });
                setShare(s.url);
              }}
              title="Share public transcript link"
            >
              🔗 Share
            </button>
          </div>
        </div>
      </div>

      {/* Role Banner */}
      <div className={`role-banner ${isClient ? "viewer" : isOwnerOrPM ? "owner" : "editor"}`}>
        <div>
          <b>User: {user?.full_name} ({user?.assessment_role} · {user?.role})</b>
          <div style={{ fontSize: "0.82rem" }}>
            {isClient && "Client Viewer Mode: You can play the audio sound, write comments, export, and request revisions. Transcript text editing is locked."}
            {isTranscriber && "Transcriber Editor Mode: Edit transcripts, auto-save changes, insert timestamps, use auto-grammar, and submit for QA review."}
            {isReviewer && "Reviewer QA Mode: Verify audio sound against transcript, run automated accuracy scoring, approve or request revisions."}
            {isOwnerOrPM && "Studio Owner / PM Mode: Full editing, QA approval, pipeline execution, and delivery controls enabled."}
          </div>
        </div>

        {/* Role-Based Task Buttons */}
        <div className="row">
          {isTranscriber && (
            <button className="btn-task" onClick={() => setProjectStatus("Under Review", "Submitted by transcriber")}>
              📋 Submit for Review
            </button>
          )}
          {(isReviewer || isOwnerOrPM) && (
            <>
              <button className="btn-task" style={{ background: "var(--good)" }} onClick={() => setProjectStatus("Approved", "QA Approved")}>
                ✅ Approve Transcript
              </button>
              <button className="btn-task" style={{ background: "var(--bad)" }} onClick={() => setProjectStatus("Revision Requested", "Reviewer requested changes")}>
                🔄 Request Revision
              </button>
            </>
          )}
          {isClient && (
            <button className="btn-task" style={{ background: "var(--warn)", color: "#fff" }} onClick={() => setProjectStatus("Revision Requested", "Client requested revision")}>
              🔄 Request Revision
            </button>
          )}
          {isOwnerOrPM && (
            <button className="btn-task" style={{ background: "var(--good)" }} onClick={() => setProjectStatus("Delivered", "Delivered to client")}>
              🚀 Mark Delivered
            </button>
          )}
        </div>
      </div>

      {err && <p className="error">{err}</p>}
      {statusMsg && <p className="ok">{statusMsg}</p>}
      {share && <p className="ok">Public Link: <a href={share} target="_blank" rel="noreferrer">{share}</a></p>}

      {/* Audio Sound Player Bar */}
      <div className="audio-player-box">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div className="row" style={{ gap: 8 }}>
            <span style={{ fontWeight: 700, color: "#fef3c7" }}>🔊 Audio Sound Engine</span>
            <button
              className={`btn-control ${!useDenoised ? "active" : ""}`}
              onClick={() => setUseDenoised(false)}
            >
              Original Sound
            </button>
            <button
              className={`btn-control ${useDenoised ? "active" : ""}`}
              onClick={() => setUseDenoised(true)}
            >
              🧹 AI Cleaned / Denoised Sound
            </button>
          </div>
          <div className="audio-time">
            {fmtTime(currentTime)} / {fmtTime(duration)}
          </div>
        </div>

        {/* Hidden or standard HTML5 player ref */}
        {isVideo ? (
          <video
            ref={media}
            src={audioSource}
            controls
            style={{ width: "100%", maxHeight: 240, marginBottom: 8 }}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={(e) => setDuration(e.target.duration)}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onRateChange={(e) => setSpeed(e.target.playbackRate)}
          />
        ) : (
          <audio
            ref={media}
            src={audioSource}
            controls
            style={{ width: "100%", height: 38, marginBottom: 10 }}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={(e) => setDuration(e.target.duration)}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
          />
        )}

        {/* Task Control Buttons */}
        <div className="audio-controls">
          <button className="btn-control active" onClick={togglePlay}>
            {isPlaying ? "⏸ Pause (Space)" : "▶️ Play (Space)"}
          </button>
          <button className="btn-control" onClick={() => seek(-5)}>
            ⏪ -5s
          </button>
          <button className="btn-control" onClick={() => seek(5)}>
            ⏩ +5s
          </button>
          <button
            className={`btn-control ${loopSegment ? "active" : ""}`}
            onClick={() => setLoopSegment(!loopSegment)}
          >
            🔁 Loop Segment: {loopSegment ? "ON" : "OFF"}
          </button>
          <button
            className={`btn-control ${autoScroll ? "active" : ""}`}
            onClick={() => setAutoScroll(!autoScroll)}
          >
            📜 Auto-Scroll: {autoScroll ? "ON" : "OFF"}
          </button>

          <span style={{ fontSize: "0.82rem", color: "#d1c4b2", marginLeft: 8 }}>Speed:</span>
          {[0.5, 0.75, 1.0, 1.25, 1.5, 2.0].map((s) => (
            <button
              key={s}
              className={`btn-control ${speed === s ? "active" : ""}`}
              style={{ padding: "4px 8px", fontSize: "0.78rem" }}
              onClick={() => {
                setSpeed(s);
                if (media.current) media.current.playbackRate = s;
              }}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      <div className="split">
        {/* Main Content: Song & Audio Lyrics or Dialogue Turns */}
        <div className="card">
          {viewMode === "lyrics" ? (
            <div>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <div className="row" style={{ gap: 8 }}>
                  <h3 style={{ margin: 0 }}>🎵 Synchronized Song Lyrics & Vocal Track</h3>
                  <span className="badge done">Lyrics Mode</span>
                </div>
                <span className="muted" style={{ fontSize: "0.82rem" }}>
                  {(t.segments || []).length} lyric line(s) · Sound sync active
                </span>
              </div>

              {/* Karaoke Sing-Along Prompter Box */}
              <div className="lyrics-prompter">
                <div className="lyrics-prompter-header">
                  <div className="row" style={{ gap: 8 }}>
                    <span>🎵 Live Vocal Track & Song Lyrics</span>
                    {isPlaying && (
                      <div className="eq-bars">
                        <div className="eq-bar" />
                        <div className="eq-bar" />
                        <div className="eq-bar" />
                        <div className="eq-bar" />
                      </div>
                    )}
                  </div>
                  <span>
                    ⏱ {fmtTime(currentTime)} / {fmtTime(duration)}
                  </span>
                </div>

                <div className="lyrics-prompter-active">
                  {activeSegIdx >= 0 && t.segments[activeSegIdx]
                    ? t.segments[activeSegIdx].text
                    : isPlaying
                    ? "♪ [Listening to song vocal intro] ♪"
                    : "▶ Press Play or spacebar to listen to song & lyrics"}
                </div>

                <div className="lyrics-prompter-next">
                  {activeSegIdx >= 0 && t.segments[activeSegIdx + 1]
                    ? `Next: ${t.segments[activeSegIdx + 1].text}`
                    : ""}
                </div>
              </div>

              {/* Live Lyric Writer Bar (Write lyrics while song plays) */}
              {!isClient && (
                <div className="card" style={{ padding: 12, marginBottom: 14, background: "#ffffff", border: "1px solid var(--line)" }}>
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: "0.9rem", color: "#1e293b" }}>
                      ✍️ Live Lyric Writer (Sync with Playing Sound)
                    </span>
                    <span className="muted" style={{ fontSize: "0.8rem", fontFamily: "IBM Plex Mono, monospace" }}>
                      Current Song Time: <b>{fmtTime(currentTime)}</b>
                    </span>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <input
                      type="text"
                      value={liveLyricText}
                      onChange={(e) => setLiveLyricText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addLyricAtCurrentTime();
                        }
                      }}
                      placeholder="Listen to song sound and type lyric here... press Enter or click 'Stamp & Add Lyric'"
                      style={{ flex: 1, padding: "8px 12px", fontSize: "0.95rem" }}
                    />
                    <button className="btn-task" onClick={addLyricAtCurrentTime} style={{ whiteSpace: "nowrap" }}>
                      ➕ Stamp Lyric [{fmtTime(currentTime)}]
                    </button>
                    <button className="btn-task ghost" onClick={formatSongLyrics} title="Structure speech into verses & chorus">
                      ✨ Auto-Format Verses
                    </button>
                  </div>
                </div>
              )}

              {/* List of Synchronized Lyrics Cards */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(t.segments || []).map((s, i) => {
                  const isActive = activeSegIdx === i;
                  return (
                    <div
                      key={i}
                      ref={(el) => (segmentRefs.current[i] = el)}
                      className={`lyric-card ${isActive ? "active" : ""}`}
                    >
                      <button
                        className="btn-task"
                        style={{
                          background: isActive ? "#16a34a" : "var(--accent)",
                          color: "#fff",
                          padding: "4px 8px",
                          fontSize: "0.78rem",
                        }}
                        onClick={() => playSegment(s)}
                        title="Play audio starting from this lyric line"
                      >
                        ▶ {fmtTime(s.start)}
                      </button>

                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <div className="row" style={{ justifyContent: "space-between" }}>
                          <input
                            className="who"
                            value={s.speaker || "Lead Vocal"}
                            disabled={isClient}
                            style={{ width: 160, padding: "2px 6px", fontSize: "0.8rem" }}
                            onChange={(e) => {
                              const segs = t.segments.map((x, j) => (j === i ? { ...x, speaker: e.target.value } : x));
                              scheduleSave({ ...t, segments: segs });
                            }}
                          />
                          <span className="muted" style={{ fontSize: "0.75rem", fontFamily: "IBM Plex Mono, monospace" }}>
                            {Number(s.start || 0).toFixed(1)}s – {Number(s.end || s.start + 2).toFixed(1)}s
                          </span>
                        </div>
                        <input
                          type="text"
                          className="lyric-text-input"
                          readOnly={isClient}
                          value={s.text || ""}
                          placeholder="Type lyric line…"
                          onChange={(e) => {
                            const segs = t.segments.map((x, j) => (j === i ? { ...x, text: e.target.value } : x));
                            scheduleSave({ ...t, segments: segs });
                          }}
                        />
                      </div>

                      <div className="row" style={{ gap: 4 }}>
                        {!isClient && (
                          <>
                            <button
                              className="ghost btn-task"
                              style={{ fontSize: "0.75rem", padding: "3px 6px" }}
                              onClick={() => {
                                const el = media.current;
                                const stamp = el ? el.currentTime : s.start;
                                const segs = t.segments.map((x, j) => (j === i ? { ...x, start: stamp } : x));
                                scheduleSave({ ...t, segments: segs });
                              }}
                              title="Sync start timestamp to current audio time"
                            >
                              ⏱
                            </button>
                            <button
                              className="ghost btn-task"
                              style={{ fontSize: "0.75rem", padding: "3px 6px" }}
                              onClick={() => addSegmentAfter(i)}
                              title="Add lyric line below"
                            >
                              ➕
                            </button>
                            <button
                              className="ghost btn-task"
                              style={{ fontSize: "0.75rem", padding: "3px 6px", color: "var(--bad)" }}
                              onClick={() => deleteSegment(i)}
                              title="Delete this lyric line"
                            >
                              🗑
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                <h3>Interactive Dialogue Turns</h3>
                <span className="muted" style={{ fontSize: "0.82rem" }}>
                  {(t.segments || []).length} speaker turn(s) · Click ▶ to play turn sound
                </span>
              </div>

              {(t.segments || []).map((s, i) => {
                const isActive = i === activeSegIdx;
                return (
                  <div
                    className={`seg ${isActive ? "active" : ""}`}
                    key={i}
                    ref={(el) => (segmentRefs.current[i] = el)}
                  >
                    <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                      <div className="row" style={{ gap: 6 }}>
                        <button
                          className="btn-task"
                          style={{ background: isActive ? "var(--accent)" : "var(--accent-2)", color: "#fff", padding: "4px 8px" }}
                          onClick={() => playSegment(s)}
                          title="Play sound starting at this timestamp"
                        >
                          ▶ Play Turn
                        </button>
                        <input
                          className="who"
                          value={s.speaker || ""}
                          disabled={isClient}
                          style={{ width: 140, padding: "4px 8px" }}
                          onChange={(e) => {
                            const segs = t.segments.map((x, j) => (j === i ? { ...x, speaker: e.target.value } : x));
                            scheduleSave({ ...t, segments: segs });
                          }}
                        />
                      </div>

                      <div className="row" style={{ gap: 6 }}>
                        {!isClient && (
                          <button
                            className="ghost btn-task"
                            style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                            onClick={() => {
                              const el = media.current;
                              const stamp = el ? el.currentTime : s.start;
                              const segs = t.segments.map((x, j) => (j === i ? { ...x, start: stamp } : x));
                              scheduleSave({ ...t, segments: segs });
                            }}
                            title="Set start timestamp to current player position"
                          >
                            ⏱ Update Timestamp
                          </button>
                        )}
                        <span className="muted" style={{ fontSize: "0.8rem", fontFamily: "IBM Plex Mono, monospace" }}>
                          {Number(s.start || 0).toFixed(1)}s – {Number(s.end || s.start + 2).toFixed(1)}s · {(Number(s.confidence || 0.95) * 100).toFixed(0)}%
                        </span>
                        {!isClient && (
                          <>
                            <button
                              className="ghost btn-task"
                              style={{ fontSize: "0.75rem", padding: "3px 6px" }}
                              onClick={() => addSegmentAfter(i)}
                              title="Add new dialogue turn after this"
                            >
                              ➕
                            </button>
                            <button
                              className="ghost btn-task"
                              style={{ fontSize: "0.75rem", padding: "3px 6px", color: "var(--bad)" }}
                              onClick={() => deleteSegment(i)}
                              title="Delete this turn"
                            >
                              🗑
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    <textarea
                      className="editor"
                      style={{ minHeight: 64, height: 72 }}
                      readOnly={isClient}
                      value={s.text || ""}
                      onChange={(e) => {
                        const segs = t.segments.map((x, j) => (j === i ? { ...x, text: e.target.value } : x));
                        scheduleSave({ ...t, segments: segs });
                      }}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Sidebar: AI Tools, QA Score, Comments & History */}
        <div>
          {/* AI Auto Features Card */}
          <div className="card" style={{ marginBottom: 12 }}>
            <h3>🤖 AI Assistance & Quality Tools</h3>
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              {!isClient && (
                <button className="btn-task" onClick={checkGrammar}>
                  ✨ Auto-Check Grammar
                </button>
              )}
              <button className="btn-task ghost" onClick={autoScoreQA}>
                📊 Auto-Score Quality
              </button>
            </div>

            {/* QA Score Display */}
            {qaScore && (
              <div className="qa-score-card">
                <div className="qa-metric">
                  <span>Accuracy</span>
                  <b>{qaScore.accuracy_pct}%</b>
                </div>
                <div className="qa-metric">
                  <span>Completion</span>
                  <b>{qaScore.completion_pct}%</b>
                </div>
                <div className="qa-metric">
                  <span>Word Count</span>
                  <b>{qaScore.word_count}</b>
                </div>
                <div className="qa-metric">
                  <span>Speed</span>
                  <b>{qaScore.words_per_minute} wpm</b>
                </div>
              </div>
            )}

            {/* Grammar Modal / Diff Preview */}
            {grammarResult && (
              <div style={{ marginTop: 12, padding: 10, background: "#fef8ee", border: "1px solid var(--line)", borderRadius: 8 }}>
                <b>Grammar Enhancement Suggestions ({grammarResult.issues.length}):</b>
                {grammarResult.issues.length === 0 ? (
                  <p className="muted" style={{ fontSize: "0.85rem", margin: "4px 0" }}>
                    No grammar or spelling issues detected!
                  </p>
                ) : (
                  <ul style={{ paddingLeft: 16, fontSize: "0.82rem", margin: "6px 0" }}>
                    {grammarResult.issues.map((iss, idx) => (
                      <li key={idx}>
                        <span style={{ textDecoration: "line-through", color: "var(--bad)" }}>{iss.original}</span> →{" "}
                        <span style={{ color: "var(--good)", fontWeight: 600 }}>{iss.replacement}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="row" style={{ marginTop: 8 }}>
                  {!isClient && grammarResult.issues.length > 0 && (
                    <button className="btn-task" onClick={applyGrammarFixes}>
                      ⚡ Apply All Fixes
                    </button>
                  )}
                  <button className="ghost btn-task" onClick={() => setGrammarResult(null)}>
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* File Conversion & Export Card */}
          <div className="card" style={{ marginBottom: 12 }}>
            <h3>📂 Convert & Export Document</h3>
            <p className="muted" style={{ fontSize: "0.82rem", margin: "4px 0 10px" }}>
              Convert synchronized lyrics or audio transcript into multiple document formats:
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <button className="btn-convert txt" style={{ justifyContent: "center" }} onClick={() => exportAs("txt")}>
                📄 Plain Text (.txt)
              </button>
              <button className="btn-convert pdf" style={{ justifyContent: "center" }} onClick={() => exportAs("pdf")}>
                📕 PDF Document (.pdf)
              </button>
              <button className="btn-convert docx" style={{ justifyContent: "center" }} onClick={() => exportAs("docx")}>
                📘 Word (.docx)
              </button>
              <button className="btn-convert" style={{ justifyContent: "center" }} onClick={() => exportAs("srt")}>
                🎬 Subtitles (.srt)
              </button>
            </div>
            {!isClient && (
              <button
                className="btn-task ghost"
                style={{ width: "100%", marginTop: 10, fontSize: "0.82rem" }}
                onClick={formatSongLyrics}
              >
                🎵 Auto-Structure Song Sections
              </button>
            )}
          </div>

          {/* Comments & Notes */}
          <div className="card">
            <h3>Discussion & Review Notes</h3>
            {comments.map((c) => (
              <p key={c.id} style={{ fontSize: "0.88rem", borderBottom: "1px dashed var(--line)", paddingBottom: 6 }}>
                <b>{c.user_name}</b>: {c.body}
              </p>
            ))}
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if (!note.trim()) return;
                await api(`/transcripts/${tid}/comments`, { method: "POST", body: JSON.stringify({ body: note }) });
                setNote("");
                load();
              }}
            >
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Leave feedback or reviewer note. Use @email to mention team members"
                style={{ minHeight: 70 }}
              />
              <button className="btn-task" style={{ marginTop: 8 }}>Post Note</button>
            </form>
          </div>

          {/* Version History */}
          <div className="card" style={{ marginTop: 12 }}>
            <h3>Revision History</h3>
            {versions.map((v) => (
              <div className="row" key={v.id} style={{ justifyContent: "space-between", marginBottom: 6, fontSize: "0.85rem" }}>
                <span>v{v.version} · {v.note || "Edit"}</span>
                {!isClient && (
                  <button
                    className="ghost btn-task"
                    style={{ fontSize: "0.75rem", padding: "2px 8px" }}
                    onClick={() => api(`/transcripts/${tid}/restore/${v.version}`, { method: "POST" }).then(load)}
                  >
                    Restore
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Reviews() {
  const [rows, setRows] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [form, setForm] = useState({ transcript_id: "", accuracy_pct: 95, completion_pct: 100, reviewer_score: 4.5, notes: "" });
  const load = () => {
    api("/reviews").then(setRows).catch(() => setRows([]));
    api("/transcripts").then(setTranscripts);
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Review & QA</h1>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          await api(`/transcripts/${form.transcript_id}/reviews`, { method: "POST", body: JSON.stringify(form) });
          load();
        }}
      >
        <label>
          Transcript
          <select value={form.transcript_id} onChange={(e) => setForm({ ...form, transcript_id: e.target.value })}>
            <option value="">Select</option>
            {transcripts.map((t) => (
              <option key={t.id} value={t.id}>
                {t.project_title}
              </option>
            ))}
          </select>
        </label>
        <div className="row">
          <label>Accuracy %<input type="number" value={form.accuracy_pct} onChange={(e) => setForm({ ...form, accuracy_pct: Number(e.target.value) })} /></label>
          <label>Completion %<input type="number" value={form.completion_pct} onChange={(e) => setForm({ ...form, completion_pct: Number(e.target.value) })} /></label>
          <label>Reviewer score<input type="number" step="0.1" value={form.reviewer_score} onChange={(e) => setForm({ ...form, reviewer_score: Number(e.target.value) })} /></label>
        </div>
        <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Reviewer comments" />
        <button>Submit review</button>
      </form>
      <div className="card" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Accuracy</th>
              <th>Completion</th>
              <th>Score</th>
              <th>TAT hours</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.status}</td>
                <td>{r.accuracy_pct}</td>
                <td>{r.completion_pct}</td>
                <td>{r.reviewer_score}</td>
                <td>{Number(r.turnaround_hours).toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ClientPortal() {
  const [projects, setProjects] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [msg, setMsg] = useState("");
  const [pid, setPid] = useState("");
  const load = () => {
    api("/projects").then(setProjects);
    api("/billing/invoices").then(setInvoices).catch(() => []);
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Client portal</h1>
      <p className="muted">Upload media, track status, download transcripts, request revisions, view invoices, and message the team.</p>
      {projects.map((p) => (
        <div className="card" key={p.id} style={{ marginBottom: 10 }}>
          <b>{p.title}</b> <span className="badge">{p.status}</span>
          <div className="row">
            <button className="ghost" onClick={() => api(`/projects/${p.id}/status`, { method: "POST", body: JSON.stringify({ status: "Revision Requested", note: "Please revise" }) }).then(load)}>
              Request revision
            </button>
          </div>
          <Uploader projectId={p.id} onDone={load} />
        </div>
      ))}
      <div className="card">
        <h3>Invoices</h3>
        {invoices.map((i) => (
          <p key={i.id}>
            {i.number} · ₹{i.total} · {i.status}
          </p>
        ))}
      </div>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          await api("/messages", { method: "POST", body: JSON.stringify({ project_id: pid, body: msg }) });
          setMsg("");
        }}
      >
        <h3>Secure message</h3>
        <select value={pid} onChange={(e) => setPid(e.target.value)}>
          <option value="">Project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <textarea value={msg} onChange={(e) => setMsg(e.target.value)} />
        <button>Send</button>
      </form>
    </div>
  );
}

function Billing() {
  const [invoices, setInvoices] = useState([]);
  const [plans, setPlans] = useState([]);
  const [method, setMethod] = useState("upi");
  const load = () => {
    api("/billing/invoices").then(setInvoices);
    api("/plans").then(setPlans);
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Billing</h1>
      <div className="row">
        <button onClick={() => api("/billing/invoices", { method: "POST", body: JSON.stringify({ billing_mode: "per_project" }) }).then(load)}>Invoice project</button>
        <button className="ghost" onClick={() => api("/billing/invoices", { method: "POST", body: JSON.stringify({ billing_mode: "per_minute", minutes: 12 }) }).then(load)}>
          Invoice 12 minutes
        </button>
        <button className="ghost" onClick={() => api("/billing/invoices", { method: "POST", body: JSON.stringify({ billing_mode: "subscription" }) }).then(load)}>
          Subscription invoice
        </button>
      </div>
      <div className="grid kpis" style={{ marginTop: 12 }}>
        {plans.map((p) => (
          <div className="card" key={p.id}>
            <b>{p.name}</b>
            <p>₹{p.price_inr} · {p.monthly_credits} credits</p>
            <button className="ghost" onClick={() => api("/orgs/plan", { method: "POST", body: JSON.stringify({ plan_id: p.id }) })}>
              Switch plan
            </button>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <label>
          Pay with
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="upi">UPI</option>
            <option value="credit_card">Credit card</option>
            <option value="debit_card">Debit card</option>
            <option value="paypal">PayPal</option>
            <option value="bank_transfer">Bank transfer</option>
          </select>
        </label>
        {invoices.map((i) => (
          <div className="row" key={i.id} style={{ justifyContent: "space-between" }}>
            <span>
              {i.number} · ₹{i.total} tax ₹{i.tax} · {i.status}
            </span>
            {i.status !== "paid" && (
              <button onClick={() => api(`/billing/invoices/${i.id}/pay`, { method: "POST", body: JSON.stringify({ method, card_number: "4242424242424242" }) }).then(load)}>
                Pay
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Reports() {
  const [prod, setProd] = useState([]);
  const [kpis, setKpis] = useState(null);
  useEffect(() => {
    api("/reports/productivity").then(setProd).catch(() => []);
    api("/reports/kpis").then(setKpis);
  }, []);
  return (
    <div>
      <h1>Reporting</h1>
      {kpis && <pre className="card">{JSON.stringify(kpis, null, 2)}</pre>}
      <div className="card">
        <h3>User performance</h3>
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Uploads</th>
              <th>Done</th>
              <th>Failed</th>
            </tr>
          </thead>
          <tbody>
            {prod.map((r) => (
              <tr key={r.user}>
                <td>{r.user}</td>
                <td>{r.uploads}</td>
                <td>{r.done}</td>
                <td>{r.failed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Workflow() {
  const [rules, setRules] = useState([]);
  const [name, setName] = useState("Escalate overdue");
  const load = () => api("/workflow/rules").then(setRules).catch(() => setRules([]));
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Workflow automation</h1>
      <div className="row">
        <button onClick={() => api("/workflow/sla-check", { method: "POST" })}>Run SLA monitor</button>
        <form
          className="row"
          onSubmit={async (e) => {
            e.preventDefault();
            await api("/workflow/rules", { method: "POST", body: JSON.stringify({ name, trigger: "deadline.approaching", action: "notify" }) });
            load();
          }}
        >
          <input value={name} onChange={(e) => setName(e.target.value)} />
          <button>Add rule</button>
        </form>
      </div>
      {rules.map((r) => (
        <p key={r.id}>
          {r.name} · {r.trigger} → {r.action} {r.is_active ? "on" : "off"}
        </p>
      ))}
    </div>
  );
}

function Integrations() {
  const [rows, setRows] = useState([]);
  const [url, setUrl] = useState("");
  const load = () => api("/integrations").then(setRows).catch(() => setRows([]));
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Integrations</h1>
      {rows.map((r) => (
        <div className="card row" key={r.provider} style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <span>
            {r.provider} · {r.status}
          </span>
          {r.status !== "connected" && (
            <button onClick={() => api(`/integrations/${r.provider}/connect`, { method: "POST", body: JSON.stringify({}) }).then(load)}>Connect</button>
          )}
        </div>
      ))}
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          const res = await api("/integrations/google_drive/import", { method: "POST", body: JSON.stringify({ url }) });
          alert(`Imported ${res.bytes} bytes`);
        }}
      >
        <h3>Import from URL (Drive / Dropbox / Zoom recording link)</h3>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        <button>Import</button>
      </form>
    </div>
  );
}

function People() {
  const [rows, setRows] = useState([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("TRANSCRIBER");
  const [invite, setInvite] = useState("");
  const load = () => api("/orgs/members").then(setRows);
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>People</h1>
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await api("/orgs/invites", { method: "POST", body: JSON.stringify({ email, role }) });
          setInvite(r.invite_url);
        }}
      >
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {["ORG_ADMIN", "PROJECT_MANAGER", "TRANSCRIBER", "REVIEWER", "CLIENT", "BILLING_MANAGER"].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <button>Invite</button>
      </form>
      {invite && <p className="ok">Invite link: {invite}</p>}
      <table className="card">
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Active</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td>
                {u.full_name}
                <div className="muted">{u.email}</div>
              </td>
              <td>
                <select
                  value={u.role}
                  onChange={(e) => api(`/orgs/members/${u.id}`, { method: "PATCH", body: JSON.stringify({ role: e.target.value }) }).then(load)}
                >
                  {["ORG_ADMIN", "PROJECT_MANAGER", "TRANSCRIBER", "REVIEWER", "CLIENT", "BILLING_MANAGER"].map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </td>
              <td>{u.is_active ? "yes" : "no"}</td>
              <td>
                <button className="ghost" onClick={() => api(`/orgs/members/${u.id}/active`, { method: "POST", body: JSON.stringify({ is_active: !u.is_active }) }).then(load)}>
                  {u.is_active ? "Deactivate" : "Activate"}
                </button>
                <button className="danger" onClick={() => api(`/orgs/members/${u.id}`, { method: "DELETE" }).then(load)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Alerts() {
  const [rows, setRows] = useState([]);
  const load = () => api("/notifications").then(setRows);
  useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <h1>Notifications</h1>
      {rows.map((n) => (
        <div className="card" key={n.id} onClick={() => api(`/notifications/${n.id}/read`, { method: "POST" }).then(load)}>
          <b>{n.title}</b>
          <p>{n.body}</p>
          <span className="muted">{n.read ? "read" : "unread"}</span>
        </div>
      ))}
    </div>
  );
}

function Audit() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api("/audit").then(setRows).catch(() => setRows([]));
  }, []);
  return (
    <div>
      <h1>Audit log</h1>
      <table className="card">
        <thead>
          <tr>
            <th>Action</th>
            <th>Entity</th>
            <th>IP</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td>{a.action}</td>
              <td>
                {a.entity_type} {a.entity_id}
              </td>
              <td>{a.ip}</td>
              <td>{a.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Settings({ user }) {
  const [org, setOrg] = useState(null);
  const [quota, setQuota] = useState(200);
  const [pwd, setPwd] = useState({ current_password: "", new_password: "" });
  const [two, setTwo] = useState(null);
  useEffect(() => {
    api("/orgs/current").then((o) => {
      setOrg(o);
      setQuota(o.monthly_credit_quota);
    });
  }, []);
  return (
    <div>
      <h1>Settings</h1>
      <div className="card">
        <h3>Profile · {user.email}</h3>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await api("/auth/password", { method: "POST", body: JSON.stringify(pwd) });
            alert("Password updated");
          }}
        >
          <label>Current password<input type="password" value={pwd.current_password} onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} /></label>
          <label>New password<input type="password" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} /></label>
          <button>Change password</button>
        </form>
        <button
          className="ghost"
          onClick={async () => {
            const d = await api("/auth/2fa/setup", { method: "POST" });
            setTwo(d);
          }}
        >
          Set up 2FA
        </button>
        {two && (
          <p>
            Secret {two.secret}. Add to authenticator then enable with a code.
            <input
              placeholder="123456"
              onBlur={(e) => api("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ totp: e.target.value }) })}
            />
          </p>
        )}
      </div>
      {org && (
        <div className="card" style={{ marginTop: 12 }}>
          <h3>{org.name} quota</h3>
          <label>
            Monthly AudicLabs credits
            <input type="number" value={quota} onChange={(e) => setQuota(Number(e.target.value))} />
          </label>
          <button onClick={() => api("/orgs/current", { method: "PATCH", body: JSON.stringify({ monthly_credit_quota: quota }) })}>Save</button>
        </div>
      )}
    </div>
  );
}

function SearchPage() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  const [data, setData] = useState(null);
  useEffect(() => {
    if (q) api(`/search?q=${encodeURIComponent(q)}`).then(setData);
  }, [q]);
  if (!data) return <p>Search from the overview bar.</p>;
  return (
    <div>
      <h1>Results for {data.query}</h1>
      <h3>Projects</h3>
      {data.projects.map((p) => (
        <p key={p.id}>{p.title}</p>
      ))}
      <h3>People</h3>
      {data.users.map((u) => (
        <p key={u.id}>{u.full_name}</p>
      ))}
      <h3>Transcripts</h3>
      {data.transcripts.map((t) => (
        <p key={t.id} dangerouslySetInnerHTML={{ __html: (t.title || "").replace(t.highlight, `<mark class="highlight">${t.highlight}</mark>`) }} />
      ))}
    </div>
  );
}

function PublicShare() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch(`/api/public/share/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error("Link revoked or invalid");
        setData(await r.json());
      })
      .catch((e) => setErr(e.message));
  }, [token]);
  if (err) return <div className="auth"><div className="card error">{err}</div></div>;
  if (!data) return <p>Loading…</p>;
  return (
    <div className="main">
      <h1>{data.title}</h1>
      <p className="muted">Read-only public transcript</p>
      {(data.segments || []).map((s, i) => (
        <p key={i}>
          <b>{s.speaker}</b> {s.text}
        </p>
      ))}
    </div>
  );
}

function InviteAccept() {
  const { token } = useParams();
  const nav = useNavigate();
  return (
    <div className="auth">
      <div className="card">
        <h1>Accept invite</h1>
        <p>Sign in with the invited email, then confirm.</p>
        <button
          onClick={async () => {
            await api("/orgs/invites/accept", { method: "POST", body: JSON.stringify({ token }) });
            nav("/");
          }}
        >
          Accept
        </button>
      </div>
    </div>
  );
}
