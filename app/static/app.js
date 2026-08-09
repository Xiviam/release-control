const state = {
  token: localStorage.getItem("release_control_token"),
  user: null,
  projects: [],
  project: null,
  environments: [],
  releases: [],
};

const $ = (selector) => document.querySelector(selector);
const authView = $("#auth-view");
const appView = $("#app-view");

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof URLSearchParams)) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) logout();
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.error?.message || body.detail?.[0]?.msg || message;
    } catch (_) { /* response is not JSON */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.remove("hidden");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => element.classList.add("hidden"), 3500);
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("release_control_token");
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
}

async function initialize() {
  if (!state.token) return logout();
  try {
    state.user = await api("/api/v1/auth/me");
    authView.classList.add("hidden");
    appView.classList.remove("hidden");
    $("#user-email").textContent = state.user.email;
    $("#user-role").textContent = state.user.role;
    await loadProjects();
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadProjects() {
  state.projects = await api("/api/v1/projects");
  $("#project-count").textContent = state.projects.length;
  const list = $("#project-list");
  list.innerHTML = state.projects.map((project) => `
    <button class="project-item ${state.project?.id === project.id ? "active" : ""}" data-id="${project.id}">${escapeHtml(project.name)}</button>
  `).join("") || '<div class="empty-list">No projects yet</div>';
  list.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => selectProject(button.dataset.id)));
  if (!state.project && state.projects.length) await selectProject(state.projects[0].id);
}

async function selectProject(id) {
  state.project = state.projects.find((project) => project.id === id);
  if (!state.project) return;
  $("#current-project-name").textContent = state.project.name;
  $("#empty-state").classList.add("hidden");
  $("#project-view").classList.remove("hidden");
  document.querySelectorAll(".project-item").forEach((item) => item.classList.toggle("active", item.dataset.id === id));
  await refreshProject();
}

async function refreshProject() {
  if (!state.project) return;
  [state.environments, state.releases] = await Promise.all([
    api(`/api/v1/projects/${state.project.id}/environments`),
    api(`/api/v1/releases?project_id=${state.project.id}`),
  ]);
  renderEnvironments();
  renderReleases();
  await loadAudit();
}

function renderEnvironments() {
  const select = $("#environment-select");
  select.innerHTML = state.environments.map((env) => `<option value="${env.id}">${escapeHtml(env.name)}${env.requires_approval ? " · approval" : ""}</option>`).join("");
  $("#release-form button").disabled = !state.environments.length;
}

const actionMap = {
  draft: ["submit", "cancel"],
  rejected: ["submit", "cancel"],
  pending_approval: ["approve", "reject", "cancel"],
  approved: ["schedule", "deploy", "cancel"],
  scheduled: ["deploy", "cancel"],
  deploying: ["complete", "fail"],
  deployed: ["rollback"],
};

function allowedActions(release) {
  let actions = actionMap[release.status] || [];
  if (state.user.role === "developer") actions = actions.filter((item) => !["approve", "reject", "deploy", "complete", "fail", "rollback"].includes(item));
  if (state.user.role === "reviewer") actions = actions.filter((item) => ["approve", "reject"].includes(item));
  return actions;
}

function renderReleases() {
  const list = $("#release-list");
  list.innerHTML = state.releases.map((release) => `
    <article class="release-card">
      <div class="release-line">
        <div>
          <div class="release-title"><strong>${escapeHtml(release.version)}</strong><span class="status ${release.status}">${release.status.replaceAll("_", " ")}</span></div>
          <div class="release-meta">${release.commit_sha.slice(0, 10)} · ${environmentName(release.environment_id)} · lock ${release.lock_version}</div>
        </div>
      </div>
      <div class="release-actions">${allowedActions(release).map((action) => `<button class="action-button" data-release="${release.id}" data-action="${action}">${action}</button>`).join("")}</div>
    </article>
  `).join("") || '<div class="empty-list">No releases in this project</div>';
  list.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => transition(button.dataset.release, button.dataset.action)));
  const count = (statuses) => state.releases.filter((release) => statuses.includes(release.status)).length;
  $("#stat-draft").textContent = count(["draft", "rejected"]);
  $("#stat-pending").textContent = count(["pending_approval"]);
  $("#stat-progress").textContent = count(["approved", "scheduled", "deploying"]);
  $("#stat-deployed").textContent = count(["deployed"]);
}

async function transition(releaseId, action) {
  let payload = { comment: null };
  if (action === "schedule") {
    const defaultTime = new Date(Date.now() + 3600_000).toISOString();
    const scheduledAt = prompt("Deployment time (ISO 8601 with timezone)", defaultTime);
    if (!scheduledAt) return;
    payload = { scheduled_at: scheduledAt, comment: "Scheduled from dashboard" };
  } else if (["reject", "fail", "rollback", "cancel"].includes(action)) {
    const comment = prompt(`Reason for ${action}`);
    if (comment === null) return;
    payload.comment = comment;
  }
  try {
    await api(`/api/v1/releases/${releaseId}/${action}`, { method: "POST", body: JSON.stringify(payload) });
    toast(`Release action completed: ${action}`);
    await refreshProject();
  } catch (error) { toast(error.message, true); }
}

async function loadAudit() {
  const events = await api(`/api/v1/projects/${state.project.id}/audit?limit=8`);
  $("#audit-list").innerHTML = events.map((event) => `
    <div class="audit-item"><b>${escapeHtml(event.action)}</b><span>${new Date(event.created_at).toLocaleString()}</span></div>
  `).join("") || '<div class="empty-list">No audit events</div>';
}

function environmentName(id) { return state.environments.find((env) => env.id === id)?.name || "unknown"; }
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = value ?? ""; return node.innerHTML; }

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const form = new URLSearchParams({ username: data.get("email"), password: data.get("password") });
  try {
    const token = await api("/api/v1/auth/token", { method: "POST", body: form });
    state.token = token.access_token;
    localStorage.setItem("release_control_token", state.token);
    await initialize();
  } catch (error) { toast(error.message, true); }
});

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const project = await api("/api/v1/projects", { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset();
    await loadProjects();
    await selectProject(project.id);
    toast("Project created");
  } catch (error) { toast(error.message, true); }
});

$("#environment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const data = { name: form.get("name"), requires_approval: form.get("requires_approval") === "on" };
  try {
    await api(`/api/v1/projects/${state.project.id}/environments`, { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset();
    event.currentTarget.querySelector("[name=requires_approval]").checked = true;
    await refreshProject();
    toast("Environment added");
  } catch (error) { toast(error.message, true); }
});

$("#release-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.project_id = state.project.id;
  try {
    await api("/api/v1/releases", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(data) });
    event.currentTarget.reset();
    renderEnvironments();
    await refreshProject();
    toast("Release draft created");
  } catch (error) { toast(error.message, true); }
});

$("#refresh-button").addEventListener("click", refreshProject);
$("#logout-button").addEventListener("click", logout);
initialize();

