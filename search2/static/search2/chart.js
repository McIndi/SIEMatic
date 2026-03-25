// static/search2/chart.js
(function () {
  // Maximum number of rows to allow charting; above this, chart is not rendered
  const CHART_MAX_ROWS = 500;
  let chartInstance = null;

  // Get search results from the JSON element on the page
  function getResults() {
    const el = document.getElementById("search-results-json");
    if (!el) return [];
    try { 
      return JSON.parse(el.textContent || "[]"); 
    } catch (e) { 
      console.warn("[SIEMatic] Failed to parse results JSON", e); 
      return []; 
    }
  }

  // Get nested object value using dot notation (e.g., "user__name")
  function getByPath(obj, path) {
    if (!obj || !path) return undefined;
    return path.split("__").reduce((acc, k) => (acc == null ? acc : acc[k]), obj);
  }

  // Convert value to string, with high-precision formatting for dates
  function formatLabel(v) {
    if (v == null) return "";
    const s = String(v);
    const d = new Date(s);
    
    // Check if it's a valid date
    if (!isNaN(d.getTime())) {
      const pad = (n) => (n < 10 ? "0" + n : "" + n);
      const yyyy = d.getUTCFullYear();
      const mm = pad(d.getUTCMonth() + 1);
      const dd = pad(d.getUTCDate());
      const HH = pad(d.getUTCHours());
      const MM = pad(d.getUTCMinutes());
      const SS = pad(d.getUTCSeconds());
      const sss = String(d.getUTCMilliseconds()).padStart(3, '0');
      
      // Return high-precision timestamp with milliseconds
      return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}.${sss}`;
    }
    return s;
  }

  // Build chart data using scatter plot approach - no alignment issues
  function buildChartData(rows, xField, yField, byField) {
    if (!byField) {
      // Single series - use scatter plot approach
      const data = [];
      for (const row of rows) {
        const xValue = getByPath(row, xField);
        const yValue = getByPath(row, yField);
        
        if (xValue == null || yValue == null) continue;
        
        const x = formatLabel(xValue);
        const y = Number(yValue);
        
        if (x === "" || !Number.isFinite(y)) continue;
        
        data.push({ x, y });
      }
      
      return {
        datasets: [{
          label: `${yField} by ${xField}`,
          data: data,
          showLine: true,
          tension: 0.1,
          fill: false,
          pointRadius: 3
        }]
      };
    } else {
      // Multiple series - group by byField and use scatter approach for each
      const seriesMap = new Map();
      
      for (const row of rows) {
        const xValue = getByPath(row, xField);
        const yValue = getByPath(row, yField);
        const byValue = getByPath(row, byField);
        
        if (xValue == null || yValue == null || byValue == null) continue;
        
        const x = formatLabel(xValue);
        const y = Number(yValue);
        const series = String(byValue);
        
        if (x === "" || !Number.isFinite(y)) continue;
        
        if (!seriesMap.has(series)) {
          seriesMap.set(series, []);
        }
        seriesMap.get(series).push({ x, y });
      }
      
      // Create datasets using scatter approach
      const datasets = [];
      for (const [series, data] of seriesMap.entries()) {
        datasets.push({
          label: series,
          data: data,
          showLine: true,
          tension: 0.1,
          fill: false,
          pointRadius: 3
        });
      }
      
      return { datasets };
    }
  }

  // Find the chart canvas element
  function getChartCanvas() {
    return (
      document.getElementById("results-chart") ||
      document.getElementById("resultsChart") ||
      document.querySelector('canvas[data-role="results-chart"]') ||
      document.querySelector("main canvas")
    );
  }

  // Main function to render the chart
  function renderChart(form) {
    const rows = getResults();
    
    // Check if we have any data
    if (!rows.length) { 
      console.warn("[SIEMatic] No results to chart."); 
      return; 
    }
    
    // Check if we have too much data
    if (rows.length > CHART_MAX_ROWS) {
      // Clear any existing chart
      if (chartInstance) { 
        chartInstance.destroy(); 
        chartInstance = null; 
      }
      const canvas = getChartCanvas();
      if (canvas) {
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      const chartError = document.getElementById("chart-error");
      if (chartError) {
        chartError.textContent = `Too many results to chart (${rows.length}). Please refine your search.`;
        chartError.classList.remove("d-none");
      }
      return;
    }
    
    // Get form values
    const xField = form.querySelector('[name="xField"]')?.value?.trim() || "";
    const yField = form.querySelector('[name="yField"]')?.value?.trim() || "";
    const byField = form.querySelector('[name="byField"]')?.value?.trim() || "";
    const chartType = (form.querySelector('[name="chartType"]')?.value || "line").toLowerCase();
    
    // Validate required fields
    if (!xField || !yField) {
      console.warn("[SIEMatic] Select X and Y fields before generating the chart.");
      return;
    }
    
    // Get canvas and context
    const canvas = getChartCanvas();
    if (!canvas) { 
      console.warn("[SIEMatic] Chart canvas not found."); 
      return; 
    }
    const ctx = canvas.getContext("2d");
    
    // Destroy existing chart if it exists
    if (chartInstance) { 
      chartInstance.destroy(); 
      chartInstance = null; 
    }
    
    // Build chart data using scatter approach
    const chartData = buildChartData(rows, xField, yField, byField);
    
    // Use scatter chart for line charts to avoid alignment issues
    const actualChartType = (chartType === "line") ? "scatter" : chartType;
    
    // Create the chart
    chartInstance = new Chart(ctx, {
      type: actualChartType,
      data: chartData,
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { 
            display: true,
            type: 'category',  // Treat X values as categories
            grid: { display: true } 
          },
          y: { 
            beginAtZero: true, 
            display: true,
            grid: { display: true } 
          }
        },
        plugins: { 
          legend: { display: true } 
        }
      }
    });
  }

  // Initialize the chart functionality when the page loads
  document.addEventListener("DOMContentLoaded", function () {
    const chartForm = document.getElementById("chart-form");
    if (chartForm) {
      // Handle form submission to generate chart
      chartForm.addEventListener("submit", function (e) {
        e.preventDefault();
        renderChart(chartForm);
      });
    }
  });

})();
