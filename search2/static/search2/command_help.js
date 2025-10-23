  document.addEventListener('DOMContentLoaded', function() {
    var collapse = document.getElementById('commandHelpCollapse');
    var chevron = document.getElementById('commandHelpChevron');

    function updateChevron() {
      if (collapse.classList.contains('show')) {
        chevron.innerHTML = '&#9650;'; // Upward chevron
      } else {
        chevron.innerHTML = '&#9660;'; // Downward chevron
      }
    }

    if (collapse) {
      collapse.addEventListener('shown.bs.collapse', updateChevron);
      collapse.addEventListener('hidden.bs.collapse', updateChevron);
      // updateChevron();
    }

    $('#commandHelpTable').DataTable({
      paging: true,
      searching: true,
      ordering: true,
      info: true,
      pageLength: 25,
      order: [],
      responsive: true,
      layout: {
        topLeft: {
          buttons: [
            'copy', 'csv', 'excel', 'pdf', 'print'
          ]
        }
      }
    });
  });

