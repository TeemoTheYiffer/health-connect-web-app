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

    const bp = getJSON("bpData");
    if (bp) {
      lineChart("bpChart", bp.labels, [
        { label: "Systolic", data: bp.systolic, borderColor: "#e07c7c", backgroundColor: "rgba(224,124,124,0.2)", tension: 0.2 },
        { label: "Diastolic", data: bp.diastolic, borderColor: "#4ea1ff", backgroundColor: "rgba(78,161,255,0.2)", tension: 0.2 },
      ]);
    }

    const w = getJSON("weightData");
    if (w) {
      lineChart("weightChart", w.labels, [
        { label: "Weight (kg)", data: w.kg, borderColor: "#5dd39e", backgroundColor: "rgba(93,211,158,0.2)", tension: 0.2 },
      ]);
    }

    const steps = getJSON("stepsData");
    if (steps) barChart("stepsChart", steps.labels, "Steps", steps.values, "#4ea1ff");

    const cals = getJSON("caloriesData");
    if (cals) barChart("caloriesChart", cals.labels, "kcal", cals.values, "#f4b860");

    const rhr = getJSON("rhrData");
    if (rhr) {
      lineChart("rhrChart", rhr.labels, [
        { label: "Resting HR", data: rhr.values, borderColor: "#5dd39e", backgroundColor: "rgba(93,211,158,0.2)", tension: 0.2 },
      ]);
    }

    const macros = getJSON("macrosData");
    if (macros) renderMacros("macrosChart", macros);

    // Dropdown range pickers: <select data-target="canvasId" data-endpoint="/api/...">.
    document.querySelectorAll("select[data-target][data-endpoint]").forEach((sel) => {
      sel.addEventListener("change", async () => {
        const target = sel.dataset.target;
        const endpoint = sel.dataset.endpoint;
        const days = sel.value;
        sel.disabled = true;
        try {
          const res = await fetch(`${endpoint}?days=${encodeURIComponent(days)}`, {
            credentials: "same-origin",
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const body = await res.json();
          // Chart-specific dispatch, currently only macrosChart, easy to extend later.
          if (target === "macrosChart") renderMacros(target, body.chart);
        } catch (e) {
          console.error("Chart refresh failed:", e);
        } finally {
          sel.disabled = false;
        }
      });
    });
  }

  function renderMacros(canvasId, payload) {
    lineChart(canvasId, payload.labels, [
      { label: "kcal", data: payload.kcal, borderColor: "#f4b860", backgroundColor: "rgba(244,184,96,0.2)", tension: 0.2 },
      { label: "Protein g", data: payload.protein, borderColor: "#5dd39e", tension: 0.2 },
      { label: "Carbs g", data: payload.carbs, borderColor: "#4ea1ff", tension: 0.2 },
      { label: "Fat g", data: payload.fat, borderColor: "#e07c7c", tension: 0.2 },
    ]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
