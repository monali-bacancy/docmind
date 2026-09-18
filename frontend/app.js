// ===========================================================================
// DocMind frontend — knowledge bases, upload + live processing status,
// streaming chat with page citations, source viewer, feedback, metrics.
// ===========================================================================

const API = "/api/v1";
const $ = (id) => document.getElementById(id);

const state = {
  kbId: null,
  conversationId: null,
  streaming: false,
  pollTimer: null,
  fbGiven: {},        // message_id -> "up"/"down"
};

// ---------- helpers --------------------------------------------------------
function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  setTimeout(() => (t.className = "toast"), 2800);
}
function esc(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function renderAnswer(text) {
  let html = esc(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\[(\d+)\]/g, '<span class="cite" data-cite="$1">[$1]</span>');
  return html;
}
async function jget(url) { return (await fetch(url)).json(); }
async function jpost(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Request failed");
  return r.json();
}

// ---------- knowledge bases ------------------------------------------------
async function loadKBs(selectId) {
  const { knowledge_bases } = await jget(`${API}/knowledge-bases`);
  const sel = $("kbSelect");
  sel.innerHTML = "";
  for (const kb of knowledge_bases) {
    const o = document.createElement("option");
    o.value = kb.id;
    o.textContent = `${kb.name} (${kb.doc_count})`;
    sel.appendChild(o);
  }
  if (knowledge_bases.length) {
    state.kbId = selectId || knowledge_bases[0].id;
    sel.value = state.kbId;
    const kb = knowledge_bases.find((k) => k.id === state.kbId);
    $("kbTitle").textContent = kb.name;
    $("kbSub").textContent = `${kb.doc_count} documents · ${kb.chunk_count} chunks`;
    await startConversation();
    await loadDocs();
  }
}

$("kbSelect").addEventListener("change", (e) => { loadKBs(e.target.value); });

$("newKbBtn").addEventListener("click", async () => {
  const name = prompt("Name your knowledge base:");
  if (!name) return;
  const kb = await jpost(`${API}/knowledge-bases`, { name });
  toast("Knowledge base created", "success");
  loadKBs(kb.id);
});

$("deleteKbBtn").addEventListener("click", async () => {
  if (!state.kbId) return;
  if (!confirm("Delete this knowledge base and all its documents?")) return;
  await fetch(`${API}/knowledge-bases/${state.kbId}`, { method: "DELETE" });
  toast("Knowledge base deleted");
  loadKBs();
});

// ---------- documents + processing status ----------------------------------
const PIPELINE = ["uploaded", "parsed", "chunked", "embedding", "indexed", "ready"];

function pipelineHtml(status) {
  if (status === "failed") return PIPELINE.map(() => '<div class="pip failed"></div>').join("");
  const activeIdx = PIPELINE.indexOf(status === "processing" ? "uploaded" : status);
  return PIPELINE.map((_, i) => {
    let cls = "pip";
    if (i < activeIdx) cls += " done";
    else if (i === activeIdx && status !== "ready") cls += " active";
    else if (status === "ready") cls += " done";
    return `<div class="${cls}"></div>`;
  }).join("");
}

function statusLabel(d) {
  if (d.status === "ready") return `<span class="status-dot ready"></span> Ready · ${d.pages} pages · ${d.chunks} chunks`;
  if (d.status === "failed") return `<span class="status-dot failed"></span> Failed: ${esc(d.error_message || "error")}`;
  const nice = { uploaded: "Queued", processing: "Processing", parsed: "Parsed", chunked: "Chunked", embedding: "Embedding", indexed: "Indexing" }[d.status] || d.status;
  return `<span class="status-dot busy"></span> ${nice}…`;
}

async function loadDocs() {
  if (!state.kbId) return;
  const kb = await jget(`${API}/knowledge-bases/${state.kbId}`);
  const list = $("docList");
  list.innerHTML = "";
  if (!kb.documents.length) {
    list.innerHTML = '<div class="doc-sub" style="padding:2px">No documents yet. Upload one above.</div>';
  }
  let anyBusy = false;
  for (const d of kb.documents) {
    if (!["ready", "failed"].includes(d.status)) anyBusy = true;
    const li = document.createElement("div");
    li.className = "doc-item";
    li.innerHTML = `
      <div class="doc-top">
        <div class="doc-name" title="${esc(d.name)}">${esc(d.name)}</div>
        <button class="doc-del" data-id="${d.id}" title="Delete">✕</button>
      </div>
      <div class="pipeline">${pipelineHtml(d.status)}</div>
      <div class="status-row">${statusLabel(d)}</div>`;
    list.appendChild(li);
  }
  $("kbSub").textContent = `${kb.documents.length} documents`;
  // Poll while anything is still processing.
  clearTimeout(state.pollTimer);
  if (anyBusy) state.pollTimer = setTimeout(loadDocs, 1500);
}

$("docList").addEventListener("click", async (e) => {
  const btn = e.target.closest(".doc-del");
  if (!btn) return;
  await fetch(`${API}/documents/${btn.dataset.id}`, { method: "DELETE" });
  toast("Document removed");
  loadDocs();
});

// ---------- upload ---------------------------------------------------------
async function uploadFile(file) {
  if (!state.kbId) { toast("Create a knowledge base first", "error"); return; }
  const fd = new FormData();
  fd.append("file", file);
  toast(`Uploading ${file.name}…`);
  const r = await fetch(`${API}/knowledge-bases/${state.kbId}/documents`, { method: "POST", body: fd });
  if (!r.ok) { toast((await r.json()).detail || "Upload failed", "error"); return; }
  const info = await r.json();
  toast("Queued for processing", "success");
  loadDocs();
  // Fetch suggested questions once the doc is ready.
  waitForReadyThenSuggest(info.id);
}

async function waitForReadyThenSuggest(docId, tries = 0) {
  if (tries > 40) return;
  const d = await jget(`${API}/documents/${docId}`);
  if (d.status === "ready") {
    try {
      const { suggestions } = await jpost(`${API}/documents/${docId}/suggest`);
      showSuggestions(suggestions);
    } catch (_) {}
  } else if (d.status !== "failed") {
    setTimeout(() => waitForReadyThenSuggest(docId, tries + 1), 1500);
  }
}

function showSuggestions(list) {
  const box = $("suggestions");
  if (!box || !list || !list.length) return;
  box.innerHTML = '<div class="doc-sub" style="margin-bottom:4px">Suggested questions</div>';
  for (const q of list) {
    const b = document.createElement("button");
    b.className = "suggestion";
    b.textContent = q;
    b.onclick = () => { $("input").value = q; $("composer").requestSubmit(); };
    box.appendChild(b);
  }
}

$("dropzone").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadFile(e.target.files[0]); e.target.value = ""; });
["dragover", "dragenter"].forEach((ev) => $("dropzone").addEventListener(ev, (e) => { e.preventDefault(); $("dropzone").classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => $("dropzone").addEventListener(ev, (e) => { e.preventDefault(); $("dropzone").classList.remove("drag"); }));
$("dropzone").addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); });

// ---------- conversation + chat --------------------------------------------
async function startConversation() {
  const conv = await jpost(`${API}/conversations`, { kb_id: state.kbId, title: "Chat" });
  state.conversationId = conv.id;
  $("messages").innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="empty-emoji">◆</div>
      <h2>Ask anything about your documents</h2>
      <p>Answers are grounded in your files with page-level citations.</p>
      <div id="suggestions" class="suggestions"></div>
    </div>`;
}

$("newChatBtn").addEventListener("click", startConversation);
$("metricsBtn").addEventListener("click", openMetrics);

function clearEmpty() { const e = $("emptyState"); if (e) e.remove(); }

function addMsg(role, html = "") {
  clearEmpty();
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  wrap.innerHTML = `<div class="avatar">${role === "user" ? "🧑" : "◆"}</div><div class="body"><div class="bubble">${html}</div></div>`;
  $("messages").appendChild(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
  return wrap;
}

let lastSources = [];
function renderSources(bodyEl, sources) {
  lastSources = sources;
  if (!sources.length) return;
  const det = document.createElement("details");
  det.className = "sources";
  det.innerHTML = `<summary>📎 ${sources.length} source${sources.length > 1 ? "s" : ""} · click to inspect</summary>`;
  for (const s of sources) {
    const card = document.createElement("div");
    card.className = "src-card";
    card.dataset.chunk = s.chunk_id;
    card.innerHTML = `
      <div class="src-top">
        <span class="src-badge">[${s.index}] ${esc(s.document_name)} · p.${s.page_number}</span>
        <span>${Math.round(s.score * 100)}%</span>
      </div>
      <div class="score-bar"><div class="score-fill" style="width:${Math.round(s.score * 100)}%"></div></div>
      <div class="src-snippet">${esc(s.snippet)}…</div>`;
    card.onclick = () => openSource(s.chunk_id);
    det.appendChild(card);
  }
  bodyEl.appendChild(det);
}

function addFeedback(bodyEl, messageId) {
  const row = document.createElement("div");
  row.className = "msg-actions";
  row.innerHTML = `<button class="fb-btn" data-r="up">👍</button><button class="fb-btn" data-r="down">👎</button>`;
  row.querySelectorAll(".fb-btn").forEach((b) =>
    b.addEventListener("click", async () => {
      const rating = b.dataset.r;
      await jpost(`${API}/feedback`, { message_id: messageId, rating });
      row.querySelectorAll(".fb-btn").forEach((x) => x.classList.remove("active-up", "active-down"));
      b.classList.add(rating === "up" ? "active-up" : "active-down");
      toast("Thanks for the feedback", "success");
    })
  );
  bodyEl.appendChild(row);
}

async function sendMessage(text) {
  if (state.streaming || !state.conversationId) return;
  state.streaming = true; $("sendBtn").disabled = true;

  addMsg("user", esc(text));
  const aiWrap = addMsg("ai", '<div class="typing"><span></span><span></span><span></span></div>');
  const bubble = aiWrap.querySelector(".bubble");
  const body = aiWrap.querySelector(".body");
  let answer = "", started = false, messageId = null;

  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kb_id: state.kbId, conversation_id: state.conversationId, message: text }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.replace(/^data: /, "").trim();
        if (!line) continue;
        const evt = JSON.parse(line);
        if (evt.type === "sources") { messageId = evt.message_id; renderSources(body, evt.sources); }
        else if (evt.type === "token") { if (!started) { bubble.innerHTML = ""; started = true; } answer += evt.text; bubble.innerHTML = renderAnswer(answer); $("messages").scrollTop = $("messages").scrollHeight; }
        else if (evt.type === "error") { bubble.innerHTML = `<span style="color:var(--danger)">⚠ ${esc(evt.message)}</span>`; }
      }
    }
    if (messageId) addFeedback(body, messageId);
  } catch (e) {
    bubble.innerHTML = `<span style="color:var(--danger)">⚠ ${esc(e.message)}</span>`;
  } finally {
    state.streaming = false; $("sendBtn").disabled = false;
    $("messages").scrollTop = $("messages").scrollHeight;
  }
}

// citation click -> open the matching source
$("messages").addEventListener("click", (e) => {
  const c = e.target.closest(".cite");
  if (!c) return;
  const s = lastSources.find((x) => String(x.index) === c.dataset.cite);
  if (s) openSource(s.chunk_id);
});

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  $("input").value = ""; $("input").style.height = "auto";
  sendMessage(text);
});
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); } });
$("input").addEventListener("input", () => { $("input").style.height = "auto"; $("input").style.height = Math.min($("input").scrollHeight, 160) + "px"; });

// ---------- source viewer modal --------------------------------------------
async function openSource(chunkId) {
  try {
    const c = await jget(`${API}/chunks/${chunkId}`);
    $("srcDocName").textContent = c.document_name;
    $("srcMeta").textContent = `Page ${c.page_number}${c.section ? " · " + c.section : ""} · ~${c.token_count} tokens`;
    $("srcContent").textContent = c.content;
    $("sourceModal").classList.remove("hidden");
  } catch (_) { toast("Could not load source", "error"); }
}
$("closeModal").addEventListener("click", () => $("sourceModal").classList.add("hidden"));
$("sourceModal").addEventListener("click", (e) => { if (e.target.id === "sourceModal") $("sourceModal").classList.add("hidden"); });

// ---------- metrics modal --------------------------------------------------
async function openMetrics() {
  const m = await jget(`${API}/admin/metrics`);
  const grid = $("metricsGrid");
  const cells = [
    ["Knowledge Bases", m.knowledge_bases], ["Documents", m.documents], ["Chunks", m.chunks],
    ["Queries", m.queries], ["Avg Retrieval", m.avg_retrieval_ms + " ms"], ["Avg Generation", m.avg_generation_ms + " ms"],
    ["Docs Ready", m.documents_ready], ["Docs Failed", m.documents_failed], ["👍 / 👎", `${m.feedback_up} / ${m.feedback_down}`],
  ];
  grid.innerHTML = cells.map(([l, v]) => `<div class="metric"><div class="val">${v}</div><div class="lbl">${l}</div></div>`).join("");

  const { logs } = await jget(`${API}/admin/logs`);
  $("logsTable").innerHTML = logs.length
    ? logs.map((l) => `<div class="log-row"><div class="log-q" title="${esc(l.query)}">${esc(l.query)}</div><div class="log-badge">${l.total_latency_ms}ms · ${Math.round((l.top_score||0)*100)}%</div><div class="log-badge ${l.status}">${l.status}</div></div>`).join("")
    : '<div class="doc-sub">No queries yet.</div>';
  $("metricsModal").classList.remove("hidden");
}
$("closeMetrics").addEventListener("click", () => $("metricsModal").classList.add("hidden"));
$("metricsModal").addEventListener("click", (e) => { if (e.target.id === "metricsModal") $("metricsModal").classList.add("hidden"); });

// ---------- init -----------------------------------------------------------
loadKBs();
