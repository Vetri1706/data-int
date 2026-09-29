document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.getElementById("searchForm");
  const promptInput = document.getElementById("promptInput");
  const thresholdRange = document.getElementById("thresholdRange");
  const thresholdValue = document.getElementById("thresholdValue");
  const submitBtn = document.getElementById("submitBtn");
  const stepperSection = document.getElementById("stepperSection");
  const workflowDagBadge = document.getElementById("workflowDagBadge");
  const resultsSection = document.getElementById("resultsSection");
  
  // History elements
  const historyBtn = document.getElementById("historyBtn");
  const historyCount = document.getElementById("historyCount");
  const historyDrawer = document.getElementById("historyDrawer");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const historyList = document.getElementById("historyList");

  // Evidence Modal elements
  const evidenceModal = document.getElementById("evidenceModal");
  const evidenceModalTitle = document.getElementById("evidenceModalTitle");
  const evidenceModalBody = document.getElementById("evidenceModalBody");
  const closeEvidenceModalBtn = document.getElementById("closeEvidenceModalBtn");

  // Output elements
  const intentBanner = document.getElementById("intentBanner");
  const markdownOutput = document.getElementById("markdownOutput");
  const contractDisplay = document.getElementById("contractDisplay");
  const datasetTableBody = document.getElementById("datasetTableBody");
  const datasetCount = document.getElementById("datasetCount");
  const sourcesCount = document.getElementById("sourcesCount");
  const exportCsvBtn = document.getElementById("exportCsvBtn");
  const exportJsonBtn = document.getElementById("exportJsonBtn");
  const queriesList = document.getElementById("queriesList");
  const sourcesGrid = document.getElementById("sourcesGrid");

  let currentDataset = [];

  // Threshold slider event
  thresholdRange.addEventListener("input", (e) => {
    thresholdValue.textContent = parseFloat(e.target.value).toFixed(2);
  });

  // Preset Template Chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      promptInput.value = chip.getAttribute("data-prompt");
      if (promptInput.value.includes("25 * 40")) {
        thresholdRange.value = "0.85";
        thresholdValue.textContent = "0.85";
      } else {
        thresholdRange.value = "0.65";
        thresholdValue.textContent = "0.65";
      }
    });
  });

  // Tab switching
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const paneId = btn.getAttribute("data-tab");
      const pane = document.getElementById(paneId);
      if (pane) pane.classList.add("active");
    });
  });

  // Drawer handlers
  historyBtn.addEventListener("click", () => {
    loadTaskHistory();
    historyDrawer.style.display = "flex";
  });

  closeDrawerBtn.addEventListener("click", () => {
    historyDrawer.style.display = "none";
  });

  historyDrawer.addEventListener("click", (e) => {
    if (e.target === historyDrawer) {
      historyDrawer.style.display = "none";
    }
  });

  // Evidence Modal handlers
  closeEvidenceModalBtn.addEventListener("click", () => {
    evidenceModal.style.display = "none";
  });

  evidenceModal.addEventListener("click", (e) => {
    if (e.target === evidenceModal) {
      evidenceModal.style.display = "none";
    }
  });

  // Load task history count on start
  loadTaskHistory();

  // Search submission
  searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    const threshold = parseFloat(thresholdRange.value);

    // Reset & show stepper
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span class="btn-icon">⏳</span> Orchestrating Workflow DAG...`;
    stepperSection.style.display = "block";
    resultsSection.style.display = "none";
    resetStepper();
    workflowDagBadge.textContent = "Compiling Data Contract & Planning DAG...";

    try {
      activateStep(1, "Evaluating Intent...", "Classifying factual necessity against threshold");

      const response = await fetch("/v1/grounded-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          grounding_threshold: threshold,
          max_sources: 8,
        }),
      });

      if (!response.ok) {
        throw new Error(`Execution error: ${response.statusText}`);
      }

      const data = await response.json();
      currentDataset = data.dataset || [];

      // Render workflow metrics
      renderStages(data.pipeline_stages);

      if (data.workflow_stats) {
        workflowDagBadge.textContent = data.workflow_stats.dag_summary;
      }

      // Render all tabs
      renderResults(data);

      // Refresh task history
      loadTaskHistory();
    } catch (err) {
      alert("Execution Error: " + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span class="btn-icon">⚡</span> Execute Data Workflow`;
    }
  });

  function resetStepper() {
    for (let i = 1; i <= 8; i++) {
      const step = document.getElementById(`step${i}`);
      if (step) {
        step.className = "step-card";
        step.querySelector(".step-status").textContent = "Pending";
        step.querySelector(".step-desc").textContent = "-";
      }
    }
  }

  function activateStep(num, status, desc) {
    const step = document.getElementById(`step${num}`);
    if (step) {
      step.className = "step-card active";
      step.querySelector(".step-status").textContent = status;
      step.querySelector(".step-desc").textContent = desc;
    }
  }

  function completeStep(num, status, desc) {
    const step = document.getElementById(`step${num}`);
    if (step) {
      step.className = "step-card completed";
      step.querySelector(".step-status").textContent = status;
      step.querySelector(".step-desc").textContent = desc;
    }
  }

  function renderStages(stages) {
    stages.forEach(st => {
      completeStep(
        st.stage_number,
        st.status,
        `${st.description} (${st.duration_ms}ms)`
      );
    });
  }

  function renderResults(data) {
    resultsSection.style.display = "block";

    // Intent Banner
    const triggered = data.grounding_metadata.triggered_grounding;
    intentBanner.innerHTML = `
      <strong>${triggered ? "🌐 Live Grounding Workflow Executed" : "⚡ Direct Reasoning / Offline"}</strong>: 
      Prompt scored <code>${data.intent.confidence_score.toFixed(2)}</code> vs threshold <code>${data.grounding_metadata.grounding_threshold.toFixed(2)}</code>.
      Category: <code>${data.intent.category}</code> (${data.intent.trigger_type}) | Total Latency: <strong>${data.total_latency_ms}ms</strong>.
    `;

    // Markdown Synthesis
    markdownOutput.innerHTML = marked.parse(data.answer_markdown);

    // Data Contract Display
    renderContract(data.data_contract);

    // Dataset Table with Field-Level Evidence & Multi-Factor Confidence
    datasetCount.textContent = data.dataset.length;
    datasetTableBody.innerHTML = "";
    
    if (data.dataset.length === 0) {
      datasetTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No validated records extracted.</td></tr>`;
    } else {
      data.dataset.forEach((r, idx) => {
        const attrsList = Object.entries(r.key_attributes)
          .filter(([k]) => k !== "snippet_preview" && k !== "anchor_citation")
          .map(([k, v]) => `<code>${escapeHtml(k)}: ${escapeHtml(v)}</code>`)
          .join(" ");

        const statusClass = r.validation_status === "PASSED" ? "badge-status-passed" : "badge-status-warning";
        const compositePercent = (r.confidence.composite_score * 100).toFixed(1);

        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>
            <div style="font-weight: 600; color: #fff;">${escapeHtml(r.canonical_name)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);"><a href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener" style="color: var(--accent-cyan); text-decoration: none;">${escapeHtml(r.source_url)} ↗</a></div>
          </td>
          <td>
            <span class="${statusClass}">● ${escapeHtml(r.validation_status)}</span>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 3px;">${escapeHtml(r.validation_notes[0] || "")}</div>
          </td>
          <td>${attrsList}</td>
          <td>
            <div class="confidence-box" title="Authority: ${r.confidence.source_authority} | Certainty: ${r.confidence.extraction_certainty} | Agreement: ${r.confidence.cross_source_agreement} | Freshness: ${r.confidence.freshness} | Completeness: ${r.confidence.completeness}">
              <span class="confidence-score">${compositePercent}%</span>
              <span class="confidence-factors">Auth: ${(r.confidence.source_authority * 100).toFixed(0)}% • Agree: ${(r.confidence.cross_source_agreement * 100).toFixed(0)}%</span>
            </div>
          </td>
          <td>
            <button class="btn-evidence" data-record-index="${idx}">
              🔍 Inspect Evidence (${Object.keys(r.field_evidence || {}).length})
            </button>
          </td>
        `;
        datasetTableBody.appendChild(tr);
      });

      // Bind Evidence Inspection clicks
      document.querySelectorAll(".btn-evidence").forEach(btn => {
        btn.addEventListener("click", (e) => {
          const index = parseInt(e.target.getAttribute("data-record-index"), 10);
          showEvidenceModal(currentDataset[index]);
        });
      });
    }

    // Export links
    exportCsvBtn.href = `/v1/tasks/${data.id}/export/csv`;
    exportJsonBtn.href = `/v1/tasks/${data.id}/export/json`;

    // Grounding Metadata Tab
    sourcesCount.textContent = data.grounding_metadata.sources.length;
    queriesList.innerHTML = "";
    if (data.grounding_metadata.search_queries.length === 0) {
      queriesList.innerHTML = `<li>(No search queries executed — offline evaluation)</li>`;
    } else {
      data.grounding_metadata.search_queries.forEach(q => {
        const li = document.createElement("li");
        li.textContent = `• "${q}"`;
        queriesList.appendChild(li);
      });
    }

    // Sources Grid
    sourcesGrid.innerHTML = "";
    data.grounding_metadata.sources.forEach(s => {
      const card = document.createElement("div");
      card.className = "source-card";
      const liveBadge = s.is_live 
        ? `<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">● 200 OK Verified</span>`
        : ``;
      card.innerHTML = `
        <div class="source-domain">${escapeHtml(s.domain)} • Anchor [${s.index}] ${liveBadge}</div>
        <div class="source-title"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener" style="color: #fff; text-decoration: none;">${escapeHtml(s.title)} ↗</a></div>
        <div class="source-snippet">${escapeHtml(s.snippet)}</div>
      `;
      sourcesGrid.appendChild(card);
    });
  }

  function renderContract(contract) {
    if (!contract) {
      contractDisplay.innerHTML = `<p style="color: var(--text-muted);">No contract compiled (offline query).</p>`;
      return;
    }

    const fieldsList = Object.entries(contract.fields)
      .map(([k, t]) => `<span class="contract-pill">${escapeHtml(k)}: <em>${escapeHtml(t)}</em></span>`)
      .join(" ");

    const constraintsList = contract.constraints.length > 0 
      ? contract.constraints.map(c => `<span class="contract-pill" style="color: var(--accent-amber);">⚡ ${escapeHtml(c)}</span>`).join(" ")
      : `<span style="color: var(--text-muted); font-size: 0.8rem;">(No hard constraints applied)</span>`;

    const critList = contract.critical_fields
      .map(cf => `<span class="contract-pill" style="color: var(--accent-emerald);">✓ ${escapeHtml(cf)}</span>`)
      .join(" ");

    const sourcesList = contract.preferred_sources
      .map(ps => `<span class="contract-pill">🌐 ${escapeHtml(ps)}</span>`)
      .join(" ");

    contractDisplay.innerHTML = `
      <div class="contract-grid">
        <div class="contract-card">
          <h4>Target Entity Contract</h4>
          <div style="font-size: 1.1rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem;">
            <code>${escapeHtml(contract.entity)}</code>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">
            Target Count: <strong>${contract.target_count} records</strong> • Freshness: <strong>${escapeHtml(contract.freshness)}</strong>
          </div>
        </div>

        <div class="contract-card">
          <h4>Required Critical Fields</h4>
          <div class="contract-pill-list">${critList}</div>
        </div>

        <div class="contract-card" style="grid-column: span 2;">
          <h4>Contract Schema Fields & Inferred Data Types</h4>
          <div class="contract-pill-list">${fieldsList}</div>
        </div>

        <div class="contract-card" style="grid-column: span 2;">
          <h4>Active Constraints & Permitted Source Filters</h4>
          <div style="margin-bottom: 0.5rem;"><strong>Constraints:</strong> ${constraintsList}</div>
          <div><strong>Preferred Discovery Channels:</strong> ${sourcesList}</div>
        </div>
      </div>
    `;
  }

  function showEvidenceModal(record) {
    if (!record) return;
    evidenceModalTitle.textContent = `Evidence Provenance: ${record.canonical_name}`;
    evidenceModalBody.innerHTML = "";

    const compositeScore = (record.confidence.composite_score * 100).toFixed(1);
    
    // Top summary card
    const headerCard = document.createElement("div");
    headerCard.className = "evidence-field-card";
    headerCard.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span style="font-weight: 700; color: #fff; font-size: 1rem;">${escapeHtml(record.canonical_name)}</span>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Source: <a href="${escapeHtml(record.source_url)}" target="_blank" rel="noopener" style="color: var(--accent-cyan);">${escapeHtml(record.source_url)}</a></div>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 1.2rem; font-weight: 700; color: var(--accent-emerald);">${compositeScore}%</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">Composite Grounding</div>
        </div>
      </div>
      <div style="display: flex; gap: 1rem; margin-top: 0.75rem; font-size: 0.78rem; color: var(--text-secondary); border-top: 1px solid var(--border-color); padding-top: 0.5rem;">
        <span>Authority: <strong>${(record.confidence.source_authority * 100).toFixed(0)}%</strong></span>
        <span>Certainty: <strong>${(record.confidence.extraction_certainty * 100).toFixed(0)}%</strong></span>
        <span>Cross-Source: <strong>${(record.confidence.cross_source_agreement * 100).toFixed(0)}%</strong></span>
        <span>Freshness: <strong>${(record.confidence.freshness * 100).toFixed(0)}%</strong></span>
      </div>
    `;
    evidenceModalBody.appendChild(headerCard);

    // List each field evidence
    const entries = Object.entries(record.field_evidence || {});
    if (entries.length === 0) {
      evidenceModalBody.innerHTML += `<p style="color: var(--text-muted); text-align: center; padding: 1.5rem;">No discrete field quotes grounded.</p>`;
    } else {
      entries.forEach(([field, ev]) => {
        const card = document.createElement("div");
        card.className = "evidence-field-card";
        card.innerHTML = `
          <div class="evidence-field-header">
            <span class="evidence-field-name">${escapeHtml(field)}</span>
            <span style="color: var(--accent-emerald); font-weight: 600; font-size: 0.8rem;">${(ev.confidence * 100).toFixed(0)}% Confidence</span>
          </div>
          <div style="font-size: 0.9rem; font-weight: 500; color: #fff; margin-bottom: 0.35rem;">
            Extracted Value: <code>${escapeHtml(ev.value)}</code>
          </div>
          <div class="evidence-quote-box">
            ${escapeHtml(ev.quote)}
          </div>
          <div class="evidence-meta-row">
            <span>Source Type: <strong style="color: var(--accent-purple);">${escapeHtml(ev.source_type)}</strong></span>
            <span>Retrieved: ${new Date(ev.retrieved_at).toLocaleTimeString()}</span>
          </div>
        `;
        evidenceModalBody.appendChild(card);
      });
    }

    evidenceModal.style.display = "flex";
  }

  async function loadTaskHistory() {
    try {
      const res = await fetch("/v1/tasks");
      if (!res.ok) return;
      const tasks = await res.json();
      historyCount.textContent = tasks.length;

      historyList.innerHTML = "";
      if (tasks.length === 0) {
        historyList.innerHTML = `<p style="color: var(--text-muted); text-align: center;">No previous workflows recorded yet.</p>`;
        return;
      }

      tasks.forEach(t => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.innerHTML = `
          <div style="font-size: 0.75rem; color: var(--text-muted);">${new Date(t.timestamp).toLocaleString()}</div>
          <div style="font-weight: 600; margin: 0.25rem 0;">${escapeHtml(t.prompt)}</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); display: flex; gap: 0.75rem; flex-wrap: wrap;">
            <span>Category: <strong>${escapeHtml(t.category)}</strong></span>
            <span>Records: <strong>${t.records_count}</strong></span>
            <span>Latency: <strong>${t.total_latency_ms}ms</strong></span>
          </div>
          ${t.workflow_summary ? `<div style="font-size: 0.72rem; color: var(--accent-cyan); margin-top: 0.35rem; font-family: var(--font-mono);">${escapeHtml(t.workflow_summary)}</div>` : ''}
        `;
        div.addEventListener("click", async () => {
          historyDrawer.style.display = "none";
          const taskRes = await fetch(`/v1/tasks/${t.id}`);
          if (taskRes.ok) {
            const taskData = await taskRes.json();
            currentDataset = taskData.dataset || [];
            stepperSection.style.display = "block";
            renderStages(taskData.pipeline_stages);
            if (taskData.workflow_stats) {
              workflowDagBadge.textContent = taskData.workflow_stats.dag_summary;
            }
            renderResults(taskData);
          }
        });
        historyList.appendChild(div);
      });
    } catch (e) {
      console.error("Failed to load task history", e);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .toString()
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
