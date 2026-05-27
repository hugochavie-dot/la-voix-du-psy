const API = "/api";

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json();
}

function legalClass(status) {
  return `legal-${status}`;
}

function renderSources(sources) {
  const tbody = document.querySelector("#sources-table tbody");
  tbody.innerHTML = "";
  for (const s of sources) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.id}</td>
      <td>${escapeHtml(s.title || s.url || "—")}</td>
      <td>
        <select data-id="${s.id}" class="edit-level">
          ${levelOptions(s.level)}
        </select>
      </td>
      <td>
        <select data-id="${s.id}" class="edit-subject">
          ${subjectOptions(s.subject)}
        </select>
      </td>
      <td class="${legalClass(s.legal_status)}">
        <select data-id="${s.id}" class="edit-legal">
          ${legalOptions(s.legal_status)}
        </select>
      </td>
      <td>${escapeHtml(s.error_message || "")}</td>
      <td><input type="text" class="edit-tags" data-id="${s.id}" value="${escapeHtml((s.tags || []).join(", "))}" placeholder="tags" /></td>
      <td class="actions">
        <button data-action="reindex" data-id="${s.id}">Réindexer</button>
        <button data-action="delete" data-id="${s.id}">Supprimer</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
  bindTableEvents();
}

function parseTags(raw) {
  return raw.split(",").map((t) => t.trim()).filter(Boolean);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function levelOptions(selected) {
  const levels = ["L1", "L2", "L3", "mixte", "recherche_avancee"];
  return levels.map((l) => `<option ${l === selected ? "selected" : ""}>${l}</option>`).join("");
}

function subjectOptions(selected) {
  const subs = [
    "psychologie_generale", "psychologie_sociale", "psychologie_cognitive",
    "psychologie_du_developpement", "psychopathologie", "neurosciences",
    "statistiques", "methodologie_experimentale", "epistemologie",
    "psychologie_clinique", "glossaire", "quiz", "fiches_de_revision",
  ];
  return subs.map((s) => `<option value="${s}" ${s === selected ? "selected" : ""}>${s}</option>`).join("");
}

function legalOptions(selected) {
  const st = ["open_access", "created_by_user", "authorized", "unknown", "rejected"];
  return st.map((s) => `<option ${s === selected ? "selected" : ""}>${s}</option>`).join("");
}

async function loadSources() {
  const data = await fetchJSON(`${API}/sources`);
  renderSources(data);
}

function bindTableEvents() {
  document.querySelectorAll(".edit-level, .edit-subject, .edit-legal").forEach((el) => {
    el.addEventListener("change", async (e) => {
      const id = e.target.dataset.id;
      const row = e.target.closest("tr");
      const body = {
        level: row.querySelector(".edit-level").value,
        subject: row.querySelector(".edit-subject").value,
        legal_status: row.querySelector(".edit-legal").value,
        tags: parseTags(row.querySelector(".edit-tags")?.value || ""),
      };
      await fetchJSON(`${API}/sources/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    });
  });

  document.querySelectorAll(".edit-tags").forEach((el) => {
    el.addEventListener("blur", async (e) => {
      const id = e.target.dataset.id;
      await fetchJSON(`${API}/sources/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: parseTags(e.target.value) }),
      });
    });
  });

  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      if (btn.dataset.action === "delete") {
        if (!confirm("Supprimer cette source ?")) return;
        await fetchJSON(`${API}/sources/${id}`, { method: "DELETE" });
        loadSources();
      }
      if (btn.dataset.action === "reindex") {
        await fetchJSON(`${API}/sources/${id}/reindex`, { method: "POST" });
        alert("Réindexation lancée");
      }
    });
  });
}

document.getElementById("form-url").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    url: fd.get("url"),
    title: fd.get("title") || null,
    level: fd.get("level") || null,
    subject: fd.get("subject") || null,
    user_authorized: fd.get("user_authorized") === "on",
  };
  if (!body.level) delete body.level;
  if (!body.subject) delete body.subject;
  await fetchJSON(`${API}/sources/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  e.target.reset();
  loadSources();
});

document.getElementById("form-upload").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetch(`${API}/sources/upload`, { method: "POST", body: fd });
  e.target.reset();
  loadSources();
});

document.getElementById("btn-refresh").addEventListener("click", loadSources);
document.getElementById("btn-errors").addEventListener("click", async () => {
  renderSources(await fetchJSON(`${API}/errors`));
});
document.getElementById("btn-dupes").addEventListener("click", async () => {
  renderSources(await fetchJSON(`${API}/duplicates`));
});

loadSources();
