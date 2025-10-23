// static/search2/datatable.js
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var table = document.getElementById("search-results-table");
    if (table && window.jQuery && window.jQuery.fn.dataTable) {
      
      // Check if DataTable is already initialized
      if ($.fn.DataTable.isDataTable('#search-results-table')) {
        console.log("DataTable already initialized, skipping...");
        return;
      }
      
      // Custom timestamp renderer for better precision
      function renderTimestamp(data, type, row) {
        if (data && typeof data === 'object' && data !== null) {
          return JSON.stringify(data, null, 2);
        }
        if (type === 'display' || type === 'type') {
          // Check if it looks like a timestamp
          const d = new Date(data);
          if (!isNaN(d.getTime()) && typeof data === 'string' && 
              (data.includes('T') || data.includes('-'))) {
            const pad = (n) => (n < 10 ? "0" + n : "" + n);
            const yyyy = d.getUTCFullYear();
            const mm = pad(d.getUTCMonth() + 1);
            const dd = pad(d.getUTCDate());
            const HH = pad(d.getUTCHours());
            const MM = pad(d.getUTCMinutes());
            const SS = pad(d.getUTCSeconds());
            const sss = String(d.getUTCMilliseconds()).padStart(3, '0');
            return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}.${sss}`;
          }
        }
        return data;
      }

      // Get data from the embedded JSON
      const jsonScript = document.getElementById('search-results-json');
      let data = [];
      if (jsonScript) {
        try {
          data = JSON.parse(jsonScript.textContent);
        } catch (e) {
          console.error('Error parsing search results JSON:', e);
        }
      }

      // Get column definitions with timestamp formatting
      const columnDefs = [];
      const headerCells = table.querySelectorAll('thead th');
      
      // Default render for objects in all columns
      columnDefs.push({
        targets: '_all',
        render: function(data, type, row) {
          if (data && typeof data === 'object' && data !== null) {
            return JSON.stringify(data, null, 2);
          }
          return data;
        }
      });
      
      headerCells.forEach((th, index) => {
        const fieldName = th.textContent.trim().toLowerCase();
        // Apply timestamp formatting to fields that likely contain timestamps
        if (fieldName.includes('created') || fieldName.includes('time') || 
            fieldName.includes('date') || fieldName.includes('stamp')) {
          columnDefs.push({
            targets: index,
            render: renderTimestamp
          });
        }
      });

      // Convert data to array of arrays matching header order
      const headers = Array.from(headerCells).map(th => th.textContent.trim());
      const tableData = data.map(row => headers.map(h => row[h] !== undefined ? row[h] : null));

      try {
        $('#search-results-table').DataTable({
          data: tableData,
          pageLength: 25,
          order: [],
          responsive: true,
          columnDefs: columnDefs,
          layout: {
            topLeft: {
              buttons: [
                'copy', 'csv', 'excel', 'pdf', 'print'
              ]
            }
          }
        });
      } catch (error) {
        console.error("Error initializing DataTable with buttons:", error);
        // Fallback: initialize without buttons
        $('#search-results-table').DataTable({
          data: data,
          pageLength: 25,
          order: [],
          responsive: true,
          columnDefs: columnDefs,
        });
      }
    }
  });
})();
