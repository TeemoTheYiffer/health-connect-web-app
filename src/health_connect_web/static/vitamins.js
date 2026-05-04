// Client-side filter for /vitamins. Each row has data-kind and data-search; we hide
// rows that don't match the active kind chip and the search box (case-insensitive).

(function () {
  function init() {
    const tbody = document.getElementById("vitBody");
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const chips = Array.from(document.querySelectorAll(".filter-chip"));
    const search = document.getElementById("vitSearch");
    const count = document.getElementById("vitCount");
    const empty = document.getElementById("vitEmpty");

    let kind = "all";
    let query = "";

    function apply() {
      let visible = 0;
      const q = query.trim().toLowerCase();
      for (const row of rows) {
        const rowKind = row.dataset.kind || "";
        const hay = row.dataset.search || "";
        const kindMatch = kind === "all" || rowKind === kind;
        const searchMatch = !q || hay.indexOf(q) !== -1;
        const show = kindMatch && searchMatch;
        row.hidden = !show;
        if (show) visible += 1;
      }
      if (count) count.textContent = String(visible);
      if (empty) empty.hidden = visible !== 0;
    }

    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        chips.forEach((c) => c.classList.toggle("active", c === chip));
        kind = chip.dataset.kind || "all";
        apply();
      });
    });

    if (search) {
      search.addEventListener("input", () => {
        query = search.value;
        apply();
      });
    }

    apply();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
