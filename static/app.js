const form = document.getElementById("search-form");
const findBtn = document.getElementById("find-btn");
const csvBtn = document.getElementById("csv-btn");
const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const tableEl = document.getElementById("results-table");
const tbody = document.getElementById("results-body");
const playTypeSelect = document.getElementById("play_type");
const penaltyOnlyCheckbox = document.getElementById("penalty_only");
const flaggedHeader = document.querySelector("th.flagged-col");

async function loadPlayTypes() {
  try {
    const response = await fetch("/api/play-types");
    if (!response.ok) return;
    const types = await response.json();
    types.sort((a, b) => (a.text || "").localeCompare(b.text || ""));
    for (const t of types) {
      if (!t.text) continue;
      const option = document.createElement("option");
      option.value = t.text;
      option.textContent = t.text;
      if (t.text === "Punt") option.selected = true;
      playTypeSelect.appendChild(option);
    }
  } catch {
    setStatus("Could not load the play-type list from the server.", true);
  }
}

function formParams() {
  const params = new URLSearchParams();
  params.set("year", document.getElementById("year").value);
  params.set("week", document.getElementById("week").value);
  params.set("season_type", document.getElementById("season_type").value);

  const classification = document.getElementById("classification").value;
  if (classification) params.set("classification", classification);

  for (const option of playTypeSelect.selectedOptions) {
    params.append("play_type", option.value);
  }

  const minYards = document.getElementById("min_yards").value;
  if (minYards !== "") params.set("min_yards", minYards);

  if (penaltyOnlyCheckbox.checked) params.set("penalty_only", "true");

  return params;
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function renderResults(payload) {
  const { results, summary } = payload;
  const penaltyOnly = penaltyOnlyCheckbox.checked;

  flaggedHeader.classList.toggle("hidden", !penaltyOnly);

  if (penaltyOnly && summary) {
    document.getElementById("count-offense").textContent = summary.offense;
    document.getElementById("count-defense").textContent = summary.defense;
    document.getElementById("count-unattributed").textContent = summary.unattributed;
    summaryEl.classList.remove("hidden");
  } else {
    summaryEl.classList.add("hidden");
  }

  tbody.innerHTML = "";
  for (const row of results) {
    const tr = document.createElement("tr");
    const flaggedCell = penaltyOnly
      ? `<td><span class="badge ${row.penalizedSide}">${row.penalizedSide}</span></td>`
      : "";
    tr.innerHTML = `
      <td>${row.period ?? ""}</td>
      <td>${row.clock ?? ""}</td>
      <td>${row.offense ?? ""}</td>
      <td>${row.defense ?? ""}</td>
      <td>${row.playType ?? ""}</td>
      <td>${row.yardsGained ?? ""}</td>
      ${flaggedCell}
      <td>${row.playText ?? ""}</td>
    `;
    tbody.appendChild(tr);
  }
  tableEl.classList.toggle("hidden", results.length === 0);

  setStatus(results.length === 0 ? "No plays found for that query." : `Found ${results.length} matching play(s).`);
}

async function handleSubmit(event) {
  event.preventDefault();
  findBtn.disabled = true;
  setStatus("Searching…");
  summaryEl.classList.add("hidden");
  tableEl.classList.add("hidden");

  try {
    const response = await fetch(`/api/query?${formParams().toString()}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }
    const payload = await response.json();
    renderResults(payload);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    findBtn.disabled = false;
  }
}

function handleDownload() {
  window.location.href = `/api/query.csv?${formParams().toString()}`;
}

form.addEventListener("submit", handleSubmit);
csvBtn.addEventListener("click", handleDownload);
loadPlayTypes();
