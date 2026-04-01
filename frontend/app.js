const state = {
  data: null,
  selectedRow: null,
  auditRows: [],
  followupOwners: {},
  followupQueue: {},
};

const form = document.getElementById("audit-form");
const message = document.getElementById("form-message");
const themeToggle = document.getElementById("theme-toggle");
const themeToggleLabel = document.getElementById("theme-toggle-label");
const billingFileInput = document.getElementById("billing-file");
const paperNotesSelect = document.getElementById("paper-notes-select");
const paperNotesTrigger = document.getElementById("paper-notes-trigger");
const paperNotesPanel = document.getElementById("paper-notes-panel");
const paperNotesOptions = document.getElementById("paper-notes-options");
const paperNotesClear = document.getElementById("paper-notes-clear");
const runAuditButton = document.getElementById("run-audit");
const auditProgress = document.getElementById("audit-progress");
const auditProgressText = document.getElementById("audit-progress-text");
const auditProgressPercent = document.getElementById("audit-progress-percent");
const auditProgressFill = document.getElementById("audit-progress-fill");
const queueClientSearch = document.getElementById("queue-client-search");
const queueStaffFilter = document.getElementById("queue-staff-filter");
const queueMissingOnly = document.getElementById("queue-missing-only");
const auditCardList = document.getElementById("audit-card-list");
const auditQueueCount = document.getElementById("audit-queue-count");
const mainTableEmpty = document.getElementById("main-table-empty");
const exportFollowupCsvButton = document.getElementById("export-followup-csv");
const followupActionList = document.getElementById("followup-action-list");
const followupCount = document.getElementById("followup-count");
const reportActions = document.getElementById("report-actions");
const downloadShiftNotePdfButton = document.getElementById("download-shift-note-pdf");
const downloadShiftNoteCsvButton = document.getElementById("download-shift-note-csv");
const API_BASE =
  window.location.hostname === "127.0.0.1" && window.location.port === "8000"
    ? "http://127.0.0.1:8001"
    : "";

let auditProgressTimer = null;
let auditProgressHeartbeatTimer = null;
let auditProgressValue = 0;
let auditProgressStartedAt = 0;
let paperNotesClientOptions = [];
const selectedPaperNotesClients = new Set();
const PAPER_NOTES_SELECTIONS_STORAGE_KEY = "mb.paper_notes_clients.selected";

function loadSavedPaperNotesSelections() {
  try {
    const raw = window.localStorage.getItem(PAPER_NOTES_SELECTIONS_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return;
    parsed.forEach((name) => {
      const normalized = String(name || "").trim();
      if (normalized) selectedPaperNotesClients.add(normalized);
    });
  } catch (_err) {
    // Ignore storage corruption and continue with empty selections.
  }
}

function savePaperNotesSelections() {
  try {
    window.localStorage.setItem(
      PAPER_NOTES_SELECTIONS_STORAGE_KEY,
      JSON.stringify(Array.from(selectedPaperNotesClients).sort((a, b) => a.localeCompare(b)))
    );
  } catch (_err) {
    // Ignore storage write issues (private mode/quota).
  }
}

function setReportActionsVisible(isVisible) {
  reportActions?.classList.toggle("is-hidden", !isVisible);
}

function setAuditUiRunning(isRunning) {
  const controls = form.querySelectorAll("input, button");
  controls.forEach((control) => {
    control.disabled = isRunning;
  });
  if (runAuditButton) {
    runAuditButton.textContent = isRunning ? "Running..." : "Run Audit";
  }
}

function updateAuditProgress(value, label) {
  auditProgressValue = Math.max(0, Math.min(100, value));
  if (auditProgressFill) {
    auditProgressFill.style.width = `${auditProgressValue}%`;
  }
  if (auditProgressPercent) {
    auditProgressPercent.textContent = `${Math.floor(auditProgressValue)}%`;
  }
  if (label && auditProgressText) {
    auditProgressText.textContent = label;
  }
}

function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function startAuditProgress() {
  if (auditProgressTimer) {
    clearInterval(auditProgressTimer);
    auditProgressTimer = null;
  }
  if (auditProgressHeartbeatTimer) {
    clearInterval(auditProgressHeartbeatTimer);
    auditProgressHeartbeatTimer = null;
  }
  auditProgressStartedAt = Date.now();
  if (auditProgress) {
    auditProgress.classList.remove("is-hidden");
  }
  updateAuditProgress(3, "Uploading billing file...");
  setAuditUiRunning(true);

  auditProgressTimer = setInterval(() => {
    if (auditProgressValue < 90) {
      const nextStep = 2 + Math.random() * 6;
      const nextValue = Math.min(90, auditProgressValue + nextStep);
      const label =
        nextValue < 30
          ? "Reading and validating inputs..."
          : nextValue < 60
          ? "Reconciling schedules and shift notes..."
          : "Computing exceptions and diagnostics...";
      updateAuditProgress(nextValue, label);
      return;
    }

    // Keep late-stage progress visibly active so long audits don't feel stuck.
    const elapsed = formatElapsed(Date.now() - auditProgressStartedAt);
    const pulseValues = [91, 92, 93, 94, 95, 94, 93, 92];
    const pulseIndex = Math.floor((Date.now() - auditProgressStartedAt) / 700) % pulseValues.length;
    const dots = ".".repeat((Math.floor((Date.now() - auditProgressStartedAt) / 900) % 3) + 1);
    updateAuditProgress(
      pulseValues[pulseIndex],
      `Still processing large audit${dots} elapsed ${elapsed}`
    );
  }, 650);

  auditProgressHeartbeatTimer = setInterval(() => {
    if (auditProgressValue < 90) return;
    const elapsed = formatElapsed(Date.now() - auditProgressStartedAt);
    if (auditProgressText) {
      auditProgressText.textContent = `Still processing large audit... elapsed ${elapsed}`;
    }
  }, 3000);
}

function finishAuditProgress(success) {
  if (auditProgressTimer) {
    clearInterval(auditProgressTimer);
    auditProgressTimer = null;
  }
  if (auditProgressHeartbeatTimer) {
    clearInterval(auditProgressHeartbeatTimer);
    auditProgressHeartbeatTimer = null;
  }

  if (success) {
    updateAuditProgress(100, "Audit complete. Preparing results...");
    window.setTimeout(() => {
      if (auditProgress) {
        auditProgress.classList.add("is-hidden");
      }
      updateAuditProgress(0, "Running audit...");
    }, 900);
  } else {
    if (auditProgressText) {
      auditProgressText.textContent = "Audit failed. Please review details.";
    }
    window.setTimeout(() => {
      if (auditProgress) {
        auditProgress.classList.add("is-hidden");
      }
      updateAuditProgress(0, "Running audit...");
    }, 1200);
  }

  setAuditUiRunning(false);
}

function setDefaults() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  document.getElementById("start-date").value = first.toISOString().slice(0, 10);
  document.getElementById("end-date").value = last.toISOString().slice(0, 10);
}

function toIsoFromMmDdYyyy(mmddyyyy) {
  const parts = mmddyyyy.split("/");
  if (parts.length !== 3) return null;
  const month = Number(parts[0]);
  const day = Number(parts[1]);
  const year = Number(parts[2]);
  if (!Number.isInteger(month) || !Number.isInteger(day) || !Number.isInteger(year)) return null;
  if (month < 1 || month > 12 || day < 1 || day > 31 || year < 2000 || year > 2100) return null;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

async function inferDateRangeFromBillingFile(file) {
  const text = await file.text();
  const strictLinePattern =
    /(?:^|\n)\s*[A-Z][A-Z\-.' ]+,\s*[A-Z][A-Z\-.' ]+\s+\d{9,15}\s+(\d{2}\/\d{2}\/\d{4})\s+[A-Z0-9]{2,4}\b/gm;
  const strictMatches = [];
  let match;
  while ((match = strictLinePattern.exec(text)) !== null) {
    strictMatches.push(match[1]);
  }

  const rawDates =
    strictMatches.length > 0 ? strictMatches : Array.from(text.matchAll(/\b(\d{2}\/\d{2}\/\d{4})\b/g)).map((m) => m[1]);
  const isoDates = rawDates.map(toIsoFromMmDdYyyy).filter(Boolean);
  if (!isoDates.length) return null;
  isoDates.sort();
  return {
    start: isoDates[0],
    end: isoDates[isoDates.length - 1],
  };
}

function titleCase(value) {
  return String(value || "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function inferClientsFromBillingFileText(text) {
  const pattern = /(?:^|\n)\s*([A-Z][A-Z\-.' ]+,\s*[A-Z][A-Z\-.' ]+)\s+\d{9,15}\s+\d{2}\/\d{2}\/\d{4}\s+[A-Z0-9]{2,4}\b/gm;
  const found = new Set();
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const raw = String(match[1] || "").trim();
    const parts = raw.split(",");
    const last = titleCase(parts[0] || "");
    const first = titleCase(parts.slice(1).join(" ").trim());
    const combined = `${first} ${last}`.trim();
    if (combined) found.add(combined);
  }
  return Array.from(found).sort((a, b) => a.localeCompare(b));
}

function updatePaperNotesTriggerLabel() {
  if (!paperNotesTrigger) return;
  if (selectedPaperNotesClients.size === 0) {
    paperNotesTrigger.textContent = "Paper Notes Clients";
    return;
  }
  if (selectedPaperNotesClients.size <= 2) {
    paperNotesTrigger.textContent = Array.from(selectedPaperNotesClients).join(", ");
    return;
  }
  paperNotesTrigger.textContent = `${selectedPaperNotesClients.size} clients selected`;
}

function renderPaperNotesOptions() {
  if (!paperNotesOptions) return;
  if (!paperNotesClientOptions.length) {
    paperNotesOptions.innerHTML = "<p class='muted'>Upload a billing file to load client names.</p>";
    updatePaperNotesTriggerLabel();
    return;
  }
  paperNotesOptions.innerHTML = paperNotesClientOptions
    .map(
      (name) => `
      <label class="paper-notes-option">
        <input type="checkbox" value="${escapeHtml(name)}" ${selectedPaperNotesClients.has(name) ? "checked" : ""} />
        <span>${escapeHtml(name)}</span>
      </label>
    `
    )
    .join("");

  paperNotesOptions.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const value = String(event.target.value || "");
      if (event.target.checked) selectedPaperNotesClients.add(value);
      else selectedPaperNotesClients.delete(value);
      savePaperNotesSelections();
      updatePaperNotesTriggerLabel();
    });
  });
  updatePaperNotesTriggerLabel();
}

function openPaperNotesPanel(isOpen) {
  if (!paperNotesPanel || !paperNotesTrigger) return;
  paperNotesPanel.classList.toggle("is-hidden", !isOpen);
  paperNotesTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

async function handleBillingFileSelection() {
  const selectedFile = billingFileInput.files && billingFileInput.files.length ? billingFileInput.files[0] : null;
  if (!selectedFile) return;
  try {
    const text = await selectedFile.text();
    const range = await inferDateRangeFromBillingFile(selectedFile);
    const clients = inferClientsFromBillingFileText(text);
    paperNotesClientOptions = clients;
    renderPaperNotesOptions();
    if (!range) {
      message.textContent = "Could not infer date range from billing file. Set dates manually.";
      return;
    }
    document.getElementById("start-date").value = range.start;
    document.getElementById("end-date").value = range.end;
    message.textContent = `Detected billing date range: ${range.start} to ${range.end}`;
  } catch (err) {
    message.textContent = "Could not read billing file for date inference.";
  }
}

function classifyTag(status) {
  if (status.startsWith("COMPLIANT")) return "tag-compliant";
  if (status.startsWith("CRITICAL")) return "tag-critical";
  if (status.startsWith("WARNING")) return "tag-warning";
  if (status.startsWith("REVENUE OPPORTUNITY")) return "tag-revenue";
  return "tag-review";
}

function rowPriorityScore(row) {
  const status = String(row.status || "");
  const missing = Number(row.missing_shift_notes || 0);
  if (missing > 0 || status.startsWith("CRITICAL")) return 0;
  if (status.startsWith("WARNING")) return 1;
  if (status.startsWith("REVIEW")) return 2;
  if (status.startsWith("REVENUE OPPORTUNITY")) return 3;
  return 4;
}

function buildCardKey(row) {
  return `${row.client}__${row.date}`;
}

function renderKpis(summary, rows) {
  document.getElementById("kpi-total").textContent = String(summary.total_client_days);
  document.getElementById("kpi-pct").textContent = `${summary.compliant_pct}%`;
  document.getElementById("kpi-compliant").textContent = String(summary.compliant_count);
  const criticalExcludingNoSchedule = (rows || []).filter(
    (row) =>
      String(row.status || "").startsWith("CRITICAL") &&
      String(row.status || "") !== "CRITICAL - BILLED WITHOUT SCHEDULE"
  ).length;
  document.getElementById("kpi-critical").textContent = String(criticalExcludingNoSchedule);
  document.getElementById("kpi-warning").textContent = String(summary.warning_count);
  document.getElementById("kpi-review").textContent = String(summary.review_count);
  document.getElementById("kpi-revenue").textContent = String(summary.revenue_opportunity_count);
}

function renderBreakdown(statusBreakdown) {
  const root = document.getElementById("status-breakdown");
  if (!root) return;
  const entries = Object.entries(statusBreakdown);
  const list = entries
    .map(([status, count]) => `<li><strong>${status}</strong>: ${count}</li>`)
    .join("");
  root.innerHTML = `<ul>${list}</ul>`;
}

function ownershipHint(row) {
  const status = String(row.status || "");
  const isPaperNotesExempt = Boolean(row.paper_notes_exempt);
  if (row.missing_shift_notes > 0) {
    if (isPresent(row.staff_on_schedule)) {
      return `Follow up with scheduled staff: ${row.staff_on_schedule}`;
    }
    return "Missing notes and no scheduled staff assigned for this client-day.";
  }
  if (!isPaperNotesExempt && status.startsWith("CRITICAL - BILLED WITHOUT NOTE")) {
    if (isPresent(row.staff_on_schedule)) {
      return `Collect missing shift note from scheduled staff: ${row.staff_on_schedule}`;
    }
    return "Collect missing shift note for this billed day; no scheduled staff was mapped.";
  }
  if (!isPaperNotesExempt && status.startsWith("WARNING - INCOMPLETE NOTES")) {
    if (isPresent(row.staff_on_schedule)) {
      return `Collect remaining shift notes from scheduled staff: ${row.staff_on_schedule}`;
    }
    return "Collect remaining shift notes; scheduled staff mapping is missing.";
  }
  if (!row.billed && row.shift_notes_present) {
    return "Note exists but billing is missing for this client-day.";
  }
  if (row.staff_match === false) {
    return "Scheduled staff and note staff do not match; review assignment.";
  }
  return "No immediate follow-up required.";
}

function buildAuditCardItems(rows) {
  return (rows || [])
    .map((row) => {
      const scheduledStaff = isPresent(row.staff_on_schedule) ? row.staff_on_schedule : "Unassigned in schedule";
      const noteStaff = isPresent(row.staff_on_note) ? row.staff_on_note : "No note staff";
      return {
        ...row,
        cardKey: buildCardKey(row),
        serviceCodes: (row.billing_service_codes || []).join(", ") || "NO-CODE",
        missingCount: Number(row.missing_shift_notes || 0),
        hasMissing: Number(row.missing_shift_notes || 0) > 0,
        scheduledStaff,
        noteStaff,
        priorityScore: rowPriorityScore(row),
        ownerHint: ownershipHint(row),
      };
    })
    .sort((a, b) => {
      if (a.priorityScore !== b.priorityScore) return a.priorityScore - b.priorityScore;
      if (a.missingCount !== b.missingCount) return b.missingCount - a.missingCount;
      if (a.client !== b.client) return String(a.client).localeCompare(String(b.client));
      return String(a.date).localeCompare(String(b.date));
    });
}

function ownerOptionsForCard(card) {
  const options = ["Unassigned"];
  if (card.scheduledStaff !== "Unassigned in schedule") options.push(card.scheduledStaff);
  if (card.noteStaff !== "No note staff" && !options.includes(card.noteStaff)) options.push(card.noteStaff);
  return options;
}

function exportFollowupCsv() {
  const queueItems = Object.values(state.followupQueue);
  if (queueItems.length === 0) {
    message.textContent = "No follow-up items to export.";
    return;
  }
  const rows = [
    ["Client", "Date", "Status", "Missing Notes", "Scheduled Staff", "Note Staff", "Assigned Owner", "Action"],
    ...queueItems.map((item) => [
      item.client,
      item.date,
      item.status,
      String(item.missingCount),
      item.scheduledStaff,
      item.noteStaff,
      item.owner,
      item.action,
    ]),
  ];
  const csv = rows
    .map((cols) => cols.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `followup_queue_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function renderFollowupActionList() {
  if (!followupActionList) return;
  const items = Object.values(state.followupQueue).sort((a, b) => {
    if (a.missingCount !== b.missingCount) return b.missingCount - a.missingCount;
    return `${a.client}${a.date}`.localeCompare(`${b.client}${b.date}`);
  });
  if (followupCount) {
    followupCount.textContent = `Follow-up queue: ${items.length}`;
  }
  if (items.length === 0) {
    followupActionList.innerHTML = "<p class='muted'>No follow-up items yet. Use “Add to Follow-up Queue” on a card.</p>";
    return;
  }
  followupActionList.innerHTML = items
    .map(
      (item) => `
      <article class="followup-item">
        <p><strong>${escapeHtml(item.client)}</strong> • ${escapeHtml(item.date)} • Missing Notes: ${item.missingCount}</p>
        <p class="muted">Scheduled: ${escapeHtml(item.scheduledStaff)} | Note Staff: ${escapeHtml(item.noteStaff)}</p>
        <p><strong>Owner:</strong> ${escapeHtml(item.owner)} — ${escapeHtml(item.action)}</p>
      </article>
    `
    )
    .join("");
}

function getFilteredCards() {
  const search = (queueClientSearch?.value || "").trim().toLowerCase();
  const selectedStaff = queueStaffFilter?.value || "";
  const missingOnly = Boolean(queueMissingOnly?.checked);
  return buildAuditCardItems(state.auditRows).filter((card) => {
    if (search && !String(card.client || "").toLowerCase().includes(search)) return false;
    if (selectedStaff && card.scheduledStaff !== selectedStaff) return false;
    if (missingOnly && !card.hasMissing) return false;
    return true;
  });
}

function renderAuditCards() {
  if (!auditCardList) return;
  const cards = getFilteredCards();
  auditCardList.innerHTML = "";
  if (auditQueueCount) {
    auditQueueCount.textContent = `Showing ${cards.length} of ${state.auditRows.length} client-day records`;
  }
  if (mainTableEmpty) {
    mainTableEmpty.classList.toggle("is-hidden", cards.length > 0);
  }

  cards.forEach((card) => {
    const article = document.createElement("article");
    article.className = "audit-card";
    if (card.hasMissing) article.classList.add("audit-card-missing");
    if (String(card.status || "").startsWith("CRITICAL")) article.classList.add("audit-card-critical");
    const ownerOptions = ownerOptionsForCard(card);
    const currentOwner = state.followupOwners[card.cardKey] || (card.scheduledStaff !== "Unassigned in schedule" ? card.scheduledStaff : "Unassigned");
    if (!state.followupOwners[card.cardKey]) {
      state.followupOwners[card.cardKey] = currentOwner;
    }
    article.innerHTML = `
      <div class="audit-card-head">
        <div>
          <h3>${escapeHtml(card.client)}</h3>
          <p class="muted">${escapeHtml(card.date)} • Codes: ${escapeHtml(card.serviceCodes)}</p>
        </div>
        <span class="tag ${classifyTag(card.status)}">${escapeHtml(card.status)}</span>
      </div>
      <div class="audit-card-checks">
        <span class="audit-chip">Billed: <strong>${card.billed ? "Yes" : "No"}</strong></span>
        <span class="audit-chip">Scheduled: <strong>${card.scheduled ? "Yes" : "No"}</strong></span>
        <span class="audit-chip">Notes: <strong>${card.shift_note_count}/${card.scheduled_shift_count}</strong></span>
        <span class="audit-chip audit-chip-missing">Missing Notes: <strong>${card.missingCount}</strong></span>
        ${card.paper_notes_exempt ? '<span class="audit-chip">Paper Notes Exempt</span>' : ""}
      </div>
      <div class="audit-card-staff">
        <p><strong>Scheduled Staff (When I Work):</strong> ${escapeHtml(card.scheduledStaff)}</p>
        <p><strong>Note Staff (Jotform):</strong> ${escapeHtml(card.noteStaff)}</p>
        <p><strong>Action:</strong> ${escapeHtml(card.ownerHint)}</p>
      </div>
      <div class="audit-owner-row">
        <label>Assign Follow-up Owner</label>
        <select class="audit-owner-select">
          ${ownerOptions
            .map((owner) => `<option value="${escapeHtml(owner)}" ${owner === currentOwner ? "selected" : ""}>${escapeHtml(owner)}</option>`)
            .join("")}
        </select>
      </div>
      <details class="audit-card-details">
        <summary>Show details</summary>
        <ul>
          <li><strong>Exception:</strong> ${escapeHtml(card.exception_reason || "NONE")}</li>
          <li><strong>Staff Match:</strong> ${escapeHtml(card.staff_match === null || card.staff_match === undefined ? "N/A" : card.staff_match ? "Yes" : "No")}</li>
          <li><strong>Findings:</strong> ${escapeHtml((card.findings || []).join("; ") || "NONE")}</li>
        </ul>
      </details>
      <div class="audit-card-actions">
        <button type="button" class="settings-btn audit-card-add-followup">Add to Follow-up Queue</button>
        <button type="button" class="settings-btn audit-card-open">Open Full Audit Trail</button>
      </div>
    `;
    article.querySelector(".audit-owner-select")?.addEventListener("change", (event) => {
      state.followupOwners[card.cardKey] = event.target.value;
      if (state.followupQueue[card.cardKey]) {
        state.followupQueue[card.cardKey].owner = event.target.value;
        renderFollowupActionList();
      }
    });
    article.querySelector(".audit-card-add-followup")?.addEventListener("click", () => {
      const owner = state.followupOwners[card.cardKey] || "Unassigned";
      state.followupQueue[card.cardKey] = {
        client: card.client,
        date: card.date,
        status: card.status,
        missingCount: card.missingCount,
        scheduledStaff: card.scheduledStaff,
        noteStaff: card.noteStaff,
        owner,
        action: card.ownerHint,
      };
      renderFollowupActionList();
    });
    article.querySelector(".audit-card-open")?.addEventListener("click", () => {
      state.selectedRow = card;
      renderDetailPanel();
    });
    auditCardList.appendChild(article);
  });
}

function refreshAuditQueueFilters() {
  if (!queueStaffFilter) return;
  const previous = queueStaffFilter.value;
  const staffValues = Array.from(
    new Set(
      (state.auditRows || [])
        .map((row) => (isPresent(row.staff_on_schedule) ? String(row.staff_on_schedule) : "Unassigned in schedule"))
        .filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b));
  queueStaffFilter.innerHTML = `<option value="">All Staff</option>${staffValues
    .map((staff) => `<option value="${escapeHtml(staff)}">${escapeHtml(staff)}</option>`)
    .join("")}`;
  if (staffValues.includes(previous)) {
    queueStaffFilter.value = previous;
  }
}

function initAuditQueueFilterEvents() {
  queueClientSearch?.addEventListener("input", renderAuditCards);
  queueStaffFilter?.addEventListener("change", renderAuditCards);
  queueMissingOnly?.addEventListener("change", renderAuditCards);
}

function renderExceptions(exceptions) {
  const list = document.getElementById("exception-list");
  list.innerHTML = "";
  if (!exceptions || exceptions.length === 0) {
    list.innerHTML = "<li>NONE</li>";
    return;
  }
  exceptions.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = `${row.client} ${row.date} :: ${row.status} :: ${row.reason || row.exception_reason}`;
    list.appendChild(li);
  });
}

function renderMatchingIssues(issues) {
  const list = document.getElementById("matching-list");
  if (!list) return;
  list.innerHTML = "";
  if (!issues || issues.length === 0) {
    list.innerHTML = "<li>NONE</li>";
    return;
  }
  const grouped = new Map();
  issues.forEach((issue) => {
    const key = [
      issue.source || "",
      issue.issue_type || "",
      issue.reason || "",
      issue.raw_client || "null",
    ].join("|");
    if (!grouped.has(key)) {
      grouped.set(key, {
        source: issue.source || "unknown",
        issueType: issue.issue_type || "unknown",
        reason: issue.reason || "no reason",
        rawClient: issue.raw_client || "null",
        dates: [],
        count: 0,
      });
    }
    const bucket = grouped.get(key);
    bucket.count += 1;
    if (issue.raw_date && bucket.dates.length < 3) {
      bucket.dates.push(issue.raw_date);
    }
  });

  Array.from(grouped.values())
    .sort((a, b) => b.count - a.count)
    .forEach((bucket) => {
      const li = document.createElement("li");
      const sampleDates = bucket.dates.length ? ` sample dates: ${bucket.dates.join(", ")}` : "";
      li.textContent = `[${bucket.source}] ${bucket.issueType} :: client=${bucket.rawClient} occurrences=${bucket.count} reason=${bucket.reason}${sampleDates}`;
      list.appendChild(li);
    });
}

function renderAssumptions(assumptions) {
  const list = document.getElementById("assumptions-list");
  if (!list) return;
  list.innerHTML = "";
  (assumptions || ["NONE"]).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
}

function renderJotformDiagnostics(diagnostics) {
  const root = document.getElementById("jotform-diagnostics-content");
  if (!root) return;
  if (!diagnostics || typeof diagnostics !== "object") {
    root.innerHTML = "<p class='muted'>No diagnostics available.</p>";
    return;
  }

  const blocks = [
    ["missing_client", "Missing Client", diagnostics.missing_client_count, diagnostics.missing_client_samples],
    [
      "missing_service_date",
      "Missing Service Date",
      diagnostics.missing_service_date_count,
      diagnostics.missing_service_date_samples,
    ],
    [
      "invalid_service_date",
      "Invalid Service Date",
      diagnostics.invalid_service_date_count,
      diagnostics.invalid_service_date_samples,
    ],
    [
      "out_of_range_service_date",
      "Out-of-Range Service Date",
      diagnostics.out_of_range_service_date_count,
      diagnostics.out_of_range_service_date_samples,
    ],
  ];

  root.innerHTML = blocks
    .map(([key, title, count, samples]) => {
      const sampleItems = (samples || [])
        .map(
          (sample) =>
            `<li><code>${sample.submission_id || "no-id"}</code> client=${sample.raw_client || "null"} label=${sample.raw_date_label || "null"} value=${sample.raw_date_value || "null"}</li>`
        )
        .join("");
      return `
        <details class="diagnostic-block" ${count > 0 ? "open" : ""}>
          <summary><strong>${title}</strong>: ${count}</summary>
          ${sampleItems ? `<ul>${sampleItems}</ul>` : "<p class='muted'>No samples.</p>"}
        </details>
      `;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isPresent(value) {
  return value !== undefined && value !== null && String(value).trim() !== "";
}

function getFirstPresent(obj, keys) {
  for (const key of keys) {
    if (isPresent(obj[key])) return obj[key];
  }
  return undefined;
}

function formatProvided(value) {
  return isPresent(value) ? String(value) : "Not provided by source payload";
}

function buildAuditTrailChecks(row) {
  const checks = [];
  const sessionDate = getFirstPresent(row, ["service_date", "note_service_date", "session_date"]);
  const noteClient = getFirstPresent(row, ["note_client", "session_client_name", "note_client_name"]);
  const clientIdBilling = getFirstPresent(row, ["client_medicaid_id", "medicaid_id"]);
  const clientIdNote = getFirstPresent(row, ["note_medicaid_id", "session_medicaid_id"]);
  const noteServiceCode = getFirstPresent(row, ["note_service_code", "session_service_code"]);
  const whoPerformed = getFirstPresent(row, ["note_staff_name", "staff_name", "caregiver_name"]);
  const scheduledWindow = getFirstPresent(row, ["scheduled_time_window", "scheduled_window"]);
  const noteWindow = getFirstPresent(row, ["note_time_window", "documented_window"]);
  const clockWindow = getFirstPresent(row, ["clock_window", "clock_in_out"]);
  const unitsBilled = getFirstPresent(row, ["units_billed", "billing_units"]);
  const rate = getFirstPresent(row, ["billing_rate", "rate"]);
  const signaturePresent = getFirstPresent(row, ["signature_present", "signed"]);
  const narrativePresent = getFirstPresent(row, ["narrative_present", "note_narrative_present"]);

  checks.push({
    check: "Shift note exists?",
    result: row.shift_notes_present ? "YES" : "NO",
    detail: row.shift_notes_present
      ? `Shift note count: ${row.shift_note_count}`
      : "No shift note linked to this client-day",
  });

  if (isPresent(sessionDate)) {
    checks.push({
      check: "Session date matches?",
      result: String(sessionDate) === String(row.date) ? "YES" : "NO",
      detail: `Note: ${sessionDate} vs Billing: ${row.date}`,
    });
  } else {
    checks.push({
      check: "Session date matches?",
      result: "REVIEW",
      detail: "Session/service date not included in current audit payload",
    });
  }

  checks.push({
    check: "Client name matches?",
    result: isPresent(noteClient) ? (String(noteClient).toLowerCase() === String(row.client).toLowerCase() ? "YES" : "NO") : "REVIEW",
    detail: isPresent(noteClient) ? `Note client: "${noteClient}" vs billing client: "${row.client}"` : "Note-level client name not included in current payload",
  });

  if (isPresent(clientIdBilling) && isPresent(clientIdNote)) {
    checks.push({
      check: "Medicaid ID matches?",
      result: String(clientIdBilling) === String(clientIdNote) ? "YES" : "NO",
      detail: `Billing ID: ${clientIdBilling}; Note ID: ${clientIdNote}`,
    });
  } else {
    checks.push({
      check: "Medicaid ID matches?",
      result: "REVIEW",
      detail: "Client Medicaid IDs were not available from both sources",
    });
  }

  if ((row.billing_service_codes || []).length > 0 && isPresent(noteServiceCode)) {
    const matches = row.billing_service_codes.map((code) => String(code)).includes(String(noteServiceCode));
    checks.push({
      check: "Service code matches?",
      result: matches ? "YES" : "NO",
      detail: `Billing: ${(row.billing_service_codes || []).join(", ")}; Note: ${noteServiceCode}`,
    });
  } else {
    checks.push({
      check: "Service code matches?",
      result: "REVIEW",
      detail: "Note-level service code not included in current payload",
    });
  }

  checks.push({
    check: "Who performed it?",
    result: isPresent(whoPerformed) ? "YES" : "REVIEW",
    detail: isPresent(whoPerformed) ? String(whoPerformed) : "Staff identity not included in current payload",
  });

  checks.push({
    check: "On the schedule?",
    result: row.scheduled ? "YES" : "NO",
    detail: row.scheduled
      ? `Scheduled shifts: ${row.scheduled_shift_count}`
      : "No schedule entry found for this client-day",
  });

  checks.push({
    check: "Scheduled time",
    result: isPresent(scheduledWindow) ? "YES" : "REVIEW",
    detail: formatProvided(scheduledWindow),
  });

  checks.push({
    check: "Note time",
    result: isPresent(noteWindow) ? "YES" : "REVIEW",
    detail: formatProvided(noteWindow),
  });

  checks.push({
    check: "Clock in/out",
    result: isPresent(clockWindow) ? "YES" : "REVIEW",
    detail: formatProvided(clockWindow),
  });

  checks.push({
    check: "Units billed",
    result: isPresent(unitsBilled) ? "YES" : "REVIEW",
    detail: formatProvided(unitsBilled),
  });

  checks.push({
    check: "Rate",
    result: isPresent(rate) ? "YES" : "REVIEW",
    detail: formatProvided(rate),
  });

  checks.push({
    check: "Signature",
    result: signaturePresent === true ? "YES" : signaturePresent === false ? "NO" : "REVIEW",
    detail:
      signaturePresent === true
        ? "Signed"
        : signaturePresent === false
        ? "Not signed"
        : "Signature field not included in current payload",
  });

  checks.push({
    check: "Narrative",
    result: narrativePresent === true ? "YES" : narrativePresent === false ? "NO" : "REVIEW",
    detail:
      narrativePresent === true
        ? "Narrative/activity details documented"
        : narrativePresent === false
        ? "Narrative/activity details missing"
        : "Narrative field not included in current payload",
  });

  return checks;
}

function buildAuditTrailFlags(row, checks) {
  const flags = [];
  if (row.exception_reason && row.exception_reason !== "NONE") {
    flags.push(row.exception_reason);
  }
  if (row.missing_shift_notes > 0) {
    flags.push(`Missing shift notes: ${row.missing_shift_notes}`);
  }
  if (String(row.status || "").startsWith("CRITICAL")) {
    flags.push("Critical compliance status on this client-day");
  }

  const reviewCount = checks.filter((item) => item.result === "REVIEW").length;
  if (reviewCount > 0) {
    flags.push(`${reviewCount} audit checks require review due to missing source fields`);
  }

  if (flags.length === 0) {
    flags.push("No additional flags for this client-day");
  }
  return flags;
}

function buildAuditTrailHtml(row) {
  const serviceCodes = (row.billing_service_codes || []).join(", ") || "NO-CODE";
  const checks = buildAuditTrailChecks(row);
  const flags = buildAuditTrailFlags(row, checks);
  const rowsHtml = checks
    .map((item) => {
      const resultClass =
        item.result === "YES" ? "audit-result-yes" : item.result === "NO" ? "audit-result-no" : "audit-result-review";
      return `<tr>
        <td>${escapeHtml(item.check)}</td>
        <td><span class="audit-result ${resultClass}">${escapeHtml(item.result)}</span></td>
        <td>${escapeHtml(item.detail)}</td>
      </tr>`;
    })
    .join("");

  const flagsHtml = flags.map((flag) => `<li>${escapeHtml(flag)}</li>`).join("");

  return `
    <article class="audit-trail">
      <p class="audit-trail-head">Full audit trail for selected billing line:</p>
      <h3>${escapeHtml(row.client)} - ${escapeHtml(row.date)} - ${escapeHtml(serviceCodes)} - ${escapeHtml(row.status)}</h3>
      <div class="audit-trail-table-wrap">
        <table class="audit-trail-table">
          <thead>
            <tr><th>Check</th><th>Result</th><th>Detail</th></tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
      <p class="flags-title">Flags to note</p>
      <ul class="flags-list">${flagsHtml}</ul>
    </article>
  `;
}

function renderDetailPanel() {
  const panel = document.getElementById("detail-panel");
  if (!state.selectedRow) {
    panel.textContent = "Select a row to inspect details.";
    return;
  }
  panel.innerHTML = buildAuditTrailHtml(state.selectedRow);
}

function renderAudit(data) {
  state.data = data;
  state.auditRows = data.audit_rows || [];
  state.followupOwners = {};
  state.followupQueue = {};
  renderKpis(data.summary, state.auditRows);
  renderBreakdown(data.status_breakdown);
  refreshAuditQueueFilters();
  renderAuditCards();
  renderFollowupActionList();
  renderExceptions(data.exceptions);
  renderMatchingIssues(data.matching_issues);
  renderJotformDiagnostics(data.notes_diagnostics);
  renderAssumptions(data.assumptions);
  renderDetailPanel();
}

async function runAudit(event) {
  event.preventDefault();
  const selectedFile = billingFileInput.files && billingFileInput.files.length ? billingFileInput.files[0] : null;
  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  if (!startDate || !endDate) {
    message.textContent = "Start date and end date are required.";
    return;
  }
  if (!selectedFile) {
    message.textContent = "Select a billing TXT file.";
    return;
  }

  message.textContent = "Running audit...";
  setReportActionsVisible(false);
  startAuditProgress();

  try {
    const formData = new FormData();
    formData.append("start_date", startDate);
    formData.append("end_date", endDate);
    formData.append("billing_file", selectedFile);
    formData.append("paper_notes_clients", Array.from(selectedPaperNotesClients).join(", "));
    const response = await fetch(`${API_BASE}/audit/upload`, {
      method: "POST",
      body: formData,
    });
    const raw = await response.text();
    let payload = null;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch (parseErr) {
      payload = null;
    }
    if (!response.ok || payload.error) {
      if (payload && payload.error) {
        message.textContent = payload.error;
      } else if (!response.ok && raw) {
        message.textContent = `Audit failed (${response.status}): ${raw.slice(0, 180)}`;
      } else {
        message.textContent = "Audit failed.";
      }
      finishAuditProgress(false);
      return;
    }
    if (!payload || typeof payload !== "object") {
      message.textContent = "Audit failed: server returned non-JSON response.";
      finishAuditProgress(false);
      return;
    }
    renderAudit(payload);
    message.textContent = "Audit complete.";
    setReportActionsVisible(true);
    finishAuditProgress(true);
  } catch (err) {
    message.textContent = `Request failed: ${err}`;
    finishAuditProgress(false);
  }
}

function buildAuditRequestFormData() {
  const selectedFile = billingFileInput.files && billingFileInput.files.length ? billingFileInput.files[0] : null;
  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  if (!startDate || !endDate) {
    throw new Error("Start date and end date are required.");
  }
  if (!selectedFile) {
    throw new Error("Select a billing TXT file.");
  }
  const formData = new FormData();
  formData.append("start_date", startDate);
  formData.append("end_date", endDate);
  formData.append("billing_file", selectedFile);
  formData.append("paper_notes_clients", Array.from(selectedPaperNotesClients).join(", "));
  return formData;
}

async function downloadShiftNoteAudit(endpoint, defaultExt) {
  let formData;
  try {
    formData = buildAuditRequestFormData();
  } catch (err) {
    message.textContent = String(err.message || err);
    return;
  }
  message.textContent = "Preparing report download...";
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const raw = await response.text();
      message.textContent = `Download failed (${response.status}): ${raw.slice(0, 180)}`;
      return;
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const fileNameMatch = disposition.match(/filename=\"([^\"]+)\"/i);
    const fileName = fileNameMatch ? fileNameMatch[1] : `shift_note_audit.${defaultExt}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    message.textContent = "Report download started.";
  } catch (err) {
    message.textContent = `Download failed: ${err}`;
  }
}

function toggleTheme() {
  const body = document.body;
  const next = body.dataset.theme === "light" ? "dark" : "light";
  body.dataset.theme = next;
  themeToggleLabel.textContent = next === "dark" ? "Switch to Light" : "Switch to Dark";
}

form.addEventListener("submit", runAudit);
themeToggle.addEventListener("click", toggleTheme);
billingFileInput.addEventListener("change", handleBillingFileSelection);
exportFollowupCsvButton?.addEventListener("click", exportFollowupCsv);
downloadShiftNotePdfButton?.addEventListener("click", () => {
  downloadShiftNoteAudit("/reports/shift-note/pdf", "pdf");
});
downloadShiftNoteCsvButton?.addEventListener("click", () => {
  downloadShiftNoteAudit("/reports/shift-note/csv", "csv");
});
paperNotesTrigger?.addEventListener("click", () => {
  if (!paperNotesPanel) return;
  const isOpen = !paperNotesPanel.classList.contains("is-hidden");
  openPaperNotesPanel(!isOpen);
});
paperNotesClear?.addEventListener("click", () => {
  selectedPaperNotesClients.clear();
  savePaperNotesSelections();
  renderPaperNotesOptions();
});
document.addEventListener("click", (event) => {
  if (!paperNotesSelect) return;
  if (!paperNotesSelect.contains(event.target)) {
    openPaperNotesPanel(false);
  }
});
initAuditQueueFilterEvents();
loadSavedPaperNotesSelections();
renderPaperNotesOptions();
setReportActionsVisible(false);
setDefaults();
themeToggleLabel.textContent = document.body.dataset.theme === "dark" ? "Switch to Light" : "Switch to Dark";
