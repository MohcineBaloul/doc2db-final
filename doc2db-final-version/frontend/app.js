// Use same origin so no CORS / "Failed to fetch" when page is at http://localhost:8000
const API_BASE = "";

let projectId = null;
let uploadPath = null;
let lastExtraction = null;

const el = (id) => document.getElementById(id);

/** Parse response as JSON, or return { detail: text } so callers get a message when server returns HTML/text. */
async function parseJson(res) {
  const text = await res.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: res.status === 500 ? `Server error (500): ${text.slice(0, 200)}` : text.slice(0, 200) };
  }
}

async function createProject() {
  const res = await fetch(`${API_BASE}/api/projects`, { method: "POST" });
  const data = await parseJson(res);
  if (!res.ok) {
    el("projectId").textContent = "Error: " + (data.detail || res.statusText);
    return;
  }
  projectId = data.project_id;
  el("projectId").textContent = `Project #${projectId}`;
  el("uploadBtn").disabled = false;
  el("uploadStatus").textContent = "";
  uploadPath = null;
  lastExtraction = null;
  el("extractBtn").disabled = true;
  el("resultsSection").hidden = true;
  el("previewSection").hidden = true;
}

async function uploadFile() {
  const input = el("fileInput");
  if (!input.files?.length || !projectId) return;
  const file = input.files[0];
  const form = new FormData();
  form.append("file", file);
  form.append("project_id", projectId);
  el("uploadStatus").textContent = "Uploading…";
  try {
    const res = await fetch(`${API_BASE}/api/upload?project_id=${projectId}`, {
      method: "POST",
      body: form,
    });
    const data = await parseJson(res);
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail) || "Upload failed");
    uploadPath = data.path;
    el("uploadStatus").textContent = `Uploaded: ${data.filename}`;
    el("uploadStatus").classList.add("ok");
    el("extractBtn").disabled = false;
  } catch (e) {
    el("uploadStatus").textContent = "Error: " + e.message;
    el("uploadStatus").classList.remove("ok");
  }
}

async function extractSchema() {
  if (!projectId || !uploadPath) return;
  el("extractStatus").textContent = "Calling LLM… (may take 30–60s)";
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);
    const res = await fetch(`${API_BASE}/api/extract?project_id=${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_path: uploadPath }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    const data = await parseJson(res);
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail) || "Extract failed");
    lastExtraction = data;
    el("extractStatus").textContent = "Schema extracted.";
    el("extractStatus").classList.add("ok");
    showResults(data);
    el("resultsSection").hidden = false;
  } catch (e) {
    const msg = e.name === "AbortError" ? "Request timed out (2 min). Try again or use a smaller file." : (e.message === "Failed to fetch" ? "Network error: is the server running at " + (window.location.origin || "this host") + "? Try refreshing." : e.message);
    el("extractStatus").textContent = "Error: " + msg;
    el("extractStatus").classList.remove("ok");
  }
}

function showResults(data) {
  el("ddlCode").textContent = data.sql_ddl || "-- no DDL --";
  const container = el("mermaidContainer");
  container.innerHTML = "";
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  pre.textContent = data.er_diagram || "erDiagram\n    PLACEHOLDER {}";
  container.appendChild(pre);
  mermaid.run({ nodes: [pre], suppressErrors: true }).catch(() => {});
}

function switchTab(tab) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  const activeTab = document.querySelector(`.tab[data-tab="${tab}"]`);
  const panel = el("tab" + (tab === "er" ? "Er" : "Ddl"));
  if (activeTab) activeTab.classList.add("active");
  if (panel) panel.classList.remove("hidden");
}

async function applySchema() {
  if (!projectId || !lastExtraction?.extraction_id) return;
  try {
    const res = await fetch(`${API_BASE}/api/apply-schema?project_id=${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ extraction_id: lastExtraction.extraction_id }),
    });
    const data = await parseJson(res);
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail) || "Apply failed");
    alert("Schema applied to DB.");
  } catch (e) {
    alert("Error: " + e.message);
  }
}

async function previewDb() {
  if (!projectId) return;
  try {
    const res = await fetch(`${API_BASE}/api/preview/${projectId}`);
    const data = await parseJson(res);
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Preview failed");
    const wrap = el("previewTables");
    wrap.innerHTML = "";
    if (!data.tables?.length) {
      wrap.innerHTML = "<p class='muted'>No tables yet. Apply schema first.</p>";
    } else {
      data.tables.forEach((t) => {
        const h = document.createElement("div");
        h.className = "table-name";
        h.textContent = t.table_name;
        wrap.appendChild(h);
        const table = document.createElement("table");
        const thead = document.createElement("thead");
        thead.innerHTML = "<tr>" + t.columns.map((c) => `<th>${c}</th>`).join("") + "</tr>";
        table.appendChild(thead);
        const tbody = document.createElement("tbody");
        t.rows.forEach((row) => {
          const tr = document.createElement("tr");
          tr.innerHTML = t.columns.map((c) => `<td>${row[c] ?? ""}</td>`).join("");
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
      });
    }
    el("previewSection").hidden = false;
  } catch (e) {
    el("previewTables").innerHTML = "<p class='muted'>Error: " + e.message + "</p>";
    el("previewSection").hidden = false;
  }
}

async function health() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    const data = await parseJson(res);
    el("healthStatus").textContent = data.llm_configured ? "LLM ready" : "Set OPENAI_API_KEY";
  } catch {
    el("healthStatus").textContent = "Server offline";
  }
}

el("createProject").addEventListener("click", createProject);
el("uploadBtn").addEventListener("click", uploadFile);
el("extractBtn").addEventListener("click", extractSchema);
el("applySchemaBtn").addEventListener("click", applySchema);
el("previewBtn").addEventListener("click", previewDb);

document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => switchTab(t.dataset.tab));
});

mermaid.initialize({ startOnLoad: false, theme: "dark" });
health();
