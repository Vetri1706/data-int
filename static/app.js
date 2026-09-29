document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.getElementById("searchForm");
  const promptInput = document.getElementById("promptInput");
  const thresholdRange = document.getElementById("thresholdRange");
  const thresholdValue = document.getElementById("thresholdValue");
  const submitBtn = document.getElementById("submitBtn");
  const stepperSection = document.getElementById("stepperSection");
  const resultsSection = document.getElementById("resultsSection");
  
  // History elements
  const historyBtn = document.getElementById("historyBtn");
  const historyCount = document.getElementById("historyCount");
  const historyDrawer = document.getElementById("historyDrawer");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const historyList = document.getElementById("historyList");

  // Output elements
  const intentBanner = document.getElementById("intentBanner");
  const markdownOutput = document.getElementById("markdownOutput");
  const datasetTableBody = document.getElementById("datasetTableBody");
  const datasetCount = document.getElementById("datasetCount");
  const sourcesCount = document.getElementById("sourcesCount");
  const exportCsvBtn = document.getElementById("exportCsvBtn");
  const exportJsonBtn = document.getElementById("exportJsonBtn");
  const queriesList = document.getElementById("queriesList");
  const sourcesGrid = document.getElementById("sourcesGrid");

  let currentTaskId = null;

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
      document.getElementById(paneId).classList.add("active");
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
    submitBtn.innerHTML = `<span class="btn-icon">⏳</span> Orchestrating Pipeline...`;
    stepperSection.style.display = "block";
    resultsSection.style.display = "none";
    resetStepper();

    try {
      // Simulate live stage stepper progression
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
      currentTaskId = data.id;

      // Render stage metrics
      renderStages(data.pipeline_stages);

      // Render results
      renderResults(data);

      // Update history count
      loadTaskHistory();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span class="btn-icon">⚡</span> Execute Data Workflow`;
    }
  });

  function resetStepper() {
    for (let i = 1; i <= 5; i++) {
      const step = document.getElementById(`step${i}`);
      step.className = "step-card";
      step.querySelector(".step-status").textContent = "Pending";
      step.querySelector(".step-desc").textContent = "-";
    }
  }

  function activateStep(num, status, desc) {
    const step = document.getElementById(`step${num}`);
    step.className = "step-card active";
    step.querySelector(".step-status").textContent = status;
    step.querySelector(".step-desc").textContent = desc;
  }

  function completeStep(num, status, desc) {
    const step = document.getElementById(`step${num}`);
    step.className = "step-card completed";
    step.querySelector(".step-status").textContent = status;
    step.querySelector(".step-desc").textContent = desc;
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
      <strong>${triggered ? "🌐 Live Search Grounding Triggered" : "⚡ Answered via Direct Reasoning"}</strong>: 
      Prompt scored <code>${data.intent.confidence_score.toFixed(2)}</code> against threshold <code>${data.grounding_metadata.grounding_threshold.toFixed(2)}</code>.
      Category: <code>${data.intent.category}</code> (${data.intent.trigger_type}) | Total Latency: <strong>${data.total_latency_ms}ms</strong>.
    `;

    // Markdown Synthesis
    markdownOutput.innerHTML = marked.parse(data.answer_markdown);

    // Dataset Table
    datasetCount.textContent = data.dataset.length;
    datasetTableBody.innerHTML = "";
    
    if (data.dataset.length === 0) {
      datasetTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No structured records extracted.</td></tr>`;
    } else {
      data.dataset.forEach(r => {
        const attrsList = Object.entries(r.key_attributes)
          .map(([k, v]) => `<code>${k}: ${v}</code>`)
          .join(" ");

        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${escapeHtml(r.title)}</strong></td>
          <td><span class="badge-accent">${escapeHtml(r.category)}</span></td>
          <td>${attrsList}</td>
          <td><span style="color: var(--accent-emerald); font-weight: 600;">${(r.confidence * 100).toFixed(0)}%</span></td>
          <td><a href="${r.source_url}" target="_blank" rel="noopener" style="color: var(--accent-cyan);">Visit Source ↗</a></td>
        `;
        datasetTableBody.appendChild(tr);
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
      card.innerHTML = `
        <div class="source-domain">${s.domain} • Anchor [${s.index}]</div>
        <div class="source-title"><a href="${s.url}" target="_blank" rel="noopener" style="color: #fff; text-decoration: none;">${escapeHtml(s.title)} ↗</a></div>
        <div class="source-snippet">${escapeHtml(s.snippet)}</div>
      `;
      sourcesGrid.appendChild(card);
    });
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
          <div style="font-size: 0.8rem; color: var(--text-secondary); display: flex; gap: 0.75rem;">
            <span>Category: <strong>${t.category}</strong></span>
            <span>Records: <strong>${t.records_count}</strong></span>
            <span>Latency: <strong>${t.total_latency_ms}ms</strong></span>
          </div>
        `;
        div.addEventListener("click", async () => {
          historyDrawer.style.display = "none";
          const taskRes = await fetch(`/v1/tasks/${t.id}`);
          if (taskRes.ok) {
            const taskData = await taskRes.json();
            stepperSection.style.display = "block";
            renderStages(taskData.pipeline_stages);
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
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
