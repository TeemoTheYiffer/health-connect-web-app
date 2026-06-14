// Single-flight Chart.js wiring. Destroys any pre-existing chart on the canvas
// before creating a new one (defensive against double-runs from defer ordering).

(function () {
  let inited = false;

  function getJSON(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function makeChart(canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    // Clobber any existing instance on this canvas, prevents the
    // "every render appends another chart" infinite-resize bug.
    const prior = Chart.getChart(canvas);
    if (prior) prior.destroy();
    new Chart(canvas, config);
  }

  function lineChart(canvasId, labels, datasets) {
    makeChart(canvasId, {
      type: "line",
      data: { labels, datasets },
      options: baseOptions(),
    });
  }

  function barChart(canvasId, labels, label, values, color) {
    makeChart(canvasId, {
      type: "bar",
      data: { labels, datasets: [{ label, data: values, backgroundColor: color }] },
      options: baseOptions(),
    });
  }

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { labels: { color: "#8a93a0" } } },
      scales: {
        x: { ticks: { color: "#8a93a0" }, grid: { color: "rgba(138,147,160,0.1)" } },
        y: { ticks: { color: "#8a93a0" }, grid: { color: "rgba(138,147,160,0.1)" } },
      },
    };
  }

  function init() {
    if (inited) return;
    if (typeof Chart === "undefined") {
      // Chart.js (deferred) hasn't executed yet, poll without re-dispatching events.
      setTimeout(init, 50);
      return;
    }
    inited = true;

    // Each renderer takes (canvasId, payload) and draws a chart. Used both for
    // the initial render from <script> JSON blocks and the dropdown-driven refetch.
    const RENDERERS = {
      bpChart: (id, p) => lineChart(id, p.labels, [
        { label: "Systolic", data: p.systolic, borderColor: "#e07c7c", backgroundColor: "rgba(224,124,124,0.2)", tension: 0.2 },
        { label: "Diastolic", data: p.diastolic, borderColor: "#4ea1ff", backgroundColor: "rgba(78,161,255,0.2)", tension: 0.2 },
      ]),
      weightChart: (id, p) => lineChart(id, p.labels, [
        { label: "Weight (kg)", data: p.kg, borderColor: "#5dd39e", backgroundColor: "rgba(93,211,158,0.2)", tension: 0.2 },
      ]),
      stepsChart: (id, p) => barChart(id, p.labels, "Steps", p.values, "#4ea1ff"),
      energyChart: (id, p) => lineChart(id, p.labels, [
        { label: "Consumed", data: p.consumed, borderColor: "#f4b860", backgroundColor: "rgba(244,184,96,0.2)", tension: 0.2 },
        { label: "Burned", data: p.burned, borderColor: "#e07c7c", backgroundColor: "rgba(224,124,124,0.2)", tension: 0.2 },
      ]),
      rhrChart: (id, p) => lineChart(id, p.labels, [
        { label: "Resting HR", data: p.values, borderColor: "#5dd39e", backgroundColor: "rgba(93,211,158,0.2)", tension: 0.2 },
      ]),
      macrosChart: (id, p) => lineChart(id, p.labels, [
        { label: "kcal", data: p.kcal, borderColor: "#f4b860", backgroundColor: "rgba(244,184,96,0.2)", tension: 0.2 },
        { label: "Protein g", data: p.protein, borderColor: "#5dd39e", tension: 0.2 },
        { label: "Carbs g", data: p.carbs, borderColor: "#4ea1ff", tension: 0.2 },
        { label: "Fat g", data: p.fat, borderColor: "#e07c7c", tension: 0.2 },
      ]),
    };

    // Map canvas IDs to the JSON <script> tag IDs holding their initial payload.
    const INITIAL_DATA = {
      bpChart: "bpData",
      weightChart: "weightData",
      stepsChart: "stepsData",
      energyChart: "energyData",
      rhrChart: "rhrData",
      macrosChart: "macrosData",
    };

    for (const [canvasId, dataId] of Object.entries(INITIAL_DATA)) {
      const payload = getJSON(dataId);
      if (payload && RENDERERS[canvasId]) RENDERERS[canvasId](canvasId, payload);
    }

    // Dropdown range pickers: <select data-target="canvasId" data-endpoint="/api/...">.
    // The endpoint returns either { chart: <data> } (food) or { data: <data> } (health).
    document.querySelectorAll("select[data-target][data-endpoint]").forEach((sel) => {
      sel.addEventListener("change", async () => {
        const target = sel.dataset.target;
        const endpoint = sel.dataset.endpoint;
        const days = sel.value;
        const renderer = RENDERERS[target];
        if (!renderer) {
          console.warn("No renderer for target", target);
          return;
        }
        sel.disabled = true;
        const url = `${endpoint}?days=${encodeURIComponent(days)}`;
        try {
          console.debug(`[charts] fetch ${url} -> #${target}`);
          const res = await fetch(url, { credentials: "same-origin" });
          if (!res.ok) throw new Error(`HTTP ${res.status} from ${url}`);
          const ct = res.headers.get("content-type") || "";
          if (!ct.includes("json")) {
            // Most likely an auth redirect that returned HTML. Reload to re-auth.
            throw new Error(`Non-JSON response (${ct}) from ${url}; session may have expired`);
          }
          const body = await res.json();
          const payload = body.data || body.chart; // tolerate either response shape
          if (!payload) throw new Error(`No payload in response: ${JSON.stringify(body).slice(0, 200)}`);
          renderer(target, payload);
        } catch (e) {
          console.error(`[charts] refresh failed for #${target}:`, e);
        } finally {
          sel.disabled = false;
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
