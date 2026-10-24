import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { api, clearSession, download, getOrg, setSession } from "./api";

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
    ["/upload", "Upload"],
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
          <div>{user.full_name}</div>
          <div>{user.role} · {user.assessment_role}</div>
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
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/projects/:id/editor/:tid" element={<Editor />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/transcripts" element={<Transcripts />} />
          <Route path="/reviews" element={<Reviews />} />
          <Route path="/client" element={<ClientPortal />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/users" element={<People />} />
          <Route path="/notifications" element={<Alerts />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/settings" element={<Settings user={user} />} />
          <Route path="/search" element={<SearchPage />} />
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

function ProjectDetail() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [members, setMembers] = useState([]);
  const [err, setErr] = useState("");
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
  return (
    <div>
      <div className="top">
        <div>
          <h1>{p.title}</h1>
          <p className="muted">
            {p.category} · {p.status} · deadline {p.deadline || "none"}
          </p>
        </div>
        <select
          value={p.status}
          onChange={async (e) => {
            await api(`/projects/${id}/status`, { method: "POST", body: JSON.stringify({ status: e.target.value }) });
            load();
          }}
        >
          {["Draft", "Assigned", "In Progress", "Under Review", "Revision Requested", "Approved", "Delivered", "Archived"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      {err && <p className="error">{err}</p>}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <h3>Media</h3>
          {p.media.map((m) => (
            <div key={m.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <div>
                {m.original_name}{" "}
                <span className={`badge ${m.job_status}`}>{m.job_status}</span>
                {m.job_error && <div className="error">{m.job_error}</div>}
              </div>
              <div className="row">
                {m.job_status === "failed" && (
                  <button className="ghost" onClick={() => api(`/media/${m.id}/retry`, { method: "POST" }).then(load)}>
                    Retry
                  </button>
                )}
              </div>
            </div>
          ))}
          <Uploader projectId={id} onDone={load} />
        </div>
        <div className="card">
          <h3>Assignment & timeline</h3>
          <select
            onChange={async (e) => {
              if (!e.target.value) return;
              await api(`/projects/${id}/assign`, { method: "POST", body: JSON.stringify({ user_id: e.target.value }) });
              load();
            }}
          >
            <option value="">Assign member…</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name} ({m.role})
              </option>
            ))}
          </select>
          <ul>
            {(p.timeline || []).map((h, i) => (
              <li key={i}>
                {h.from_status || "—"} → {h.to_status} · {h.note}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <TranscriptJump projectId={id} />
    </div>
  );
}

function TranscriptJump({ projectId }) {
  const [rows, setRows] = useState([]);
  const nav = useNavigate();
  useEffect(() => {
    api("/transcripts").then((all) => setRows(all.filter((t) => t.project_id === projectId)));
  }, [projectId]);
  if (!rows.length) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>Transcripts</h3>
      {rows.map((t) => (
        <button key={t.id} className="ghost" onClick={() => nav(`/projects/${projectId}/editor/${t.id}`)}>
          Open editor · v{t.current_version} · {(t.avg_confidence * 100).toFixed(0)}% confidence
        </button>
      ))}
    </div>
  );
}

function Uploader({ projectId, onDone }) {
  const [drag, setDrag] = useState(false);
  const [language, setLanguage] = useState("auto");
  const [hints, setHints] = useState("");
  const [denoise, setDenoise] = useState(true);
  const [diarize, setDiarize] = useState(true);
  const [langs, setLangs] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/lookups/languages")
      .then((d) => setLangs(d.languages || []))
      .catch(() => {});
  }, []);
  async function send(fileList) {
    setError("");
    const fd = new FormData();
    [...fileList].forEach((f) => fd.append("files", f));
    fd.append("language", language);
    fd.append("spelling_hints", hints);
    fd.append("denoise", denoise);
    fd.append("diarize", diarize);
    try {
      await api(`/projects/${projectId}/uploads`, { method: "POST", body: fd });
      onDone?.();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
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
        send(e.dataTransfer.files);
      }}
    >
      <p>{drag ? "Drop files" : "Drag audio/video here or choose files (MP3 WAV MP4 AVI MKV AAC FLAC)"}</p>
      <input type="file" multiple accept=".mp3,.wav,.mp4,.avi,.mkv,.aac,.flac,.m4a,.ogg,.webm" onChange={(e) => send(e.target.files)} />
      <label>
        Language
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="auto">Auto-detect</option>
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
      </label>
      <label>
        Spelling hints
        <input value={hints} onChange={(e) => setHints(e.target.value)} placeholder="Names, brands, jargon" />
      </label>
      <label>
        <input type="checkbox" checked={denoise} onChange={(e) => setDenoise(e.target.checked)} /> Noise suppression
      </label>
      <label>
        <input type="checkbox" checked={diarize} onChange={(e) => setDiarize(e.target.checked)} /> Speaker labels
      </label>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function UploadPage() {
  const [projects, setProjects] = useState([]);
  const [id, setId] = useState("");
  useEffect(() => {
    api("/projects").then((rows) => {
      setProjects(rows);
      if (rows[0]) setId(rows[0].id);
    });
  }, []);
  return (
    <div>
      <h1>Bulk upload</h1>
      <label>
        Project
        <select value={id} onChange={(e) => setId(e.target.value)}>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </label>
      {id && <Uploader projectId={id} />}
    </div>
  );
}

function Transcripts() {
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
        <h1>Transcript repository</h1>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Full-text search" />
          <button>Search</button>
        </form>
      </div>
      {rows.map((t) => (
        <div className="card" key={t.id} style={{ marginBottom: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <b>{t.project_title}</b>
              <div className="muted">
                {t.detected_language} · accent {t.accent_label} · {(t.avg_confidence * 100).toFixed(0)}%
              </div>
            </div>
            <button onClick={() => nav(`/projects/${t.project_id}/editor/${t.id}`)}>Open</button>
          </div>
          <p>{(t.raw_text || "").slice(0, 240)}</p>
        </div>
      ))}
    </div>
  );
}

function Editor() {
  const { id, tid } = useParams();
  const [t, setT] = useState(null);
  const [comments, setComments] = useState([]);
  const [versions, setVersions] = useState([]);
  const [note, setNote] = useState("");
  const [speed, setSpeed] = useState(1);
  const [err, setErr] = useState("");
  const [share, setShare] = useState("");
  const media = useRef();
  const saveTimer = useRef();
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
        const el = media.current;
        if (!el) return;
        el.paused ? el.play() : el.pause();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  function scheduleSave(next) {
    setT(next);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      api(`/transcripts/${tid}`, { method: "PATCH", body: JSON.stringify({ segments: next.segments, speakers: next.speakers, note: "autosave" }) }).catch(
        (e) => setErr(e.message)
      );
    }, 800);
  }
  if (!t) return <p>Loading editor…</p>;
  const isVideo = (t.media_type || "").startsWith("video");
  return (
    <div>
      <div className="top">
        <div>
          <h1>{t.project_title}</h1>
          <p className="muted">Space to play/pause · autosave on · version {t.current_version}</p>
        </div>
        <div className="row">
          <button className="ghost" onClick={() => download(`/transcripts/${tid}/export.txt`, "transcript.txt")}>TXT</button>
          <button className="ghost" onClick={() => download(`/transcripts/${tid}/export.srt`, "transcript.srt")}>SRT</button>
          <button className="ghost" onClick={() => download(`/transcripts/${tid}/export.docx`, "transcript.docx")}>DOCX</button>
          <button
            className="ghost"
            onClick={async () => {
              const s = await api(`/transcripts/${tid}/share`, { method: "POST" });
              setShare(s.url);
            }}
          >
            Share
          </button>
          <button className="ghost" onClick={() => api(`/transcripts/${tid}/share/revoke`, { method: "POST" })}>
            Revoke link
          </button>
        </div>
      </div>
      {err && <p className="error">{err}</p>}
      {share && <p className="ok">Public link: {share}</p>}
      <div className="split">
        <div className="card">
          {isVideo ? (
            <video ref={media} src={t.play_url} controls style={{ width: "100%" }} onRateChange={(e) => setSpeed(e.target.playbackRate)} />
          ) : (
            <audio ref={media} src={t.play_url} controls style={{ width: "100%" }} />
          )}
          <label>
            Speed
            <input
              type="range"
              min="0.5"
              max="2"
              step="0.25"
              value={speed}
              onChange={(e) => {
                const v = Number(e.target.value);
                setSpeed(v);
                if (media.current) media.current.playbackRate = v;
              }}
            />
            {speed}x
          </label>
          {(t.segments || []).map((s, i) => (
            <div className="seg" key={i}>
              <div className="row">
                <input
                  className="who"
                  value={s.speaker || ""}
                  onChange={(e) => {
                    const segs = t.segments.map((x, j) => (j === i ? { ...x, speaker: e.target.value } : x));
                    scheduleSave({ ...t, segments: segs });
                  }}
                />
                <button
                  className="ghost"
                  onClick={() => {
                    const el = media.current;
                    const stamp = el ? el.currentTime : s.start;
                    const segs = t.segments.map((x, j) => (j === i ? { ...x, start: stamp } : x));
                    scheduleSave({ ...t, segments: segs });
                  }}
                >
                  Insert timestamp
                </button>
                <span className="muted">{Number(s.start || 0).toFixed(1)}s · {(Number(s.confidence || 0.9) * 100).toFixed(0)}%</span>
              </div>
              <textarea
                className="editor"
                value={s.text || ""}
                onChange={(e) => {
                  const segs = t.segments.map((x, j) => (j === i ? { ...x, text: e.target.value } : x));
                  scheduleSave({ ...t, segments: segs });
                }}
              />
            </div>
          ))}
        </div>
        <div>
          <div className="card">
            <h3>Comments</h3>
            {comments.map((c) => (
              <p key={c.id}>
                <b>{c.user_name}</b> {c.body}
              </p>
            ))}
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await api(`/transcripts/${tid}/comments`, { method: "POST", body: JSON.stringify({ body: note }) });
                setNote("");
                load();
              }}
            >
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Thread note. Mention with @email" />
              <button>Comment</button>
            </form>
          </div>
          <div className="card" style={{ marginTop: 12 }}>
            <h3>Version history</h3>
            {versions.map((v) => (
              <div className="row" key={v.id}>
                <span>
                  v{v.version} · {v.note}
                </span>
                <button className="ghost" onClick={() => api(`/transcripts/${tid}/restore/${v.version}`, { method: "POST" }).then(load)}>
                  Restore
                </button>
              </div>
            ))}
          </div>
          <div className="card" style={{ marginTop: 12 }}>
            <button
              className="ghost"
              onClick={async () => {
                const g = await api(`/transcripts/${tid}/grammar`, { method: "POST" });
                alert(`${g.issues.length} issues. Suggested text copied to console.`);
                console.log(g.fixed_text);
              }}
            >
              Grammar check
            </button>
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
