// static/search2/visualization_selector.js
(function () {
  function $(sel, root = document) { return root.querySelector(sel); }

  function setViz(mode) {
    const table = $("#table-viz");
    const chart = $("#chart-viz");
    if (!table || !chart) return;
    if (mode === "chart") {
      table.classList.add("d-none");
      chart.classList.remove("d-none");
    } else {
      chart.classList.add("d-none");
      table.classList.remove("d-none");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const vizSelect = $("#viz-select");
    if (vizSelect) {
      setViz((vizSelect.value || "table").toLowerCase());
      vizSelect.addEventListener("change", function (e) {
        const v = (e.target.value || "").toLowerCase();
        setViz(v);
      }, { passive: true });
    }
  });
})();
