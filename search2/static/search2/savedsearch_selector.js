document.addEventListener('DOMContentLoaded', function() {
  var selector = document.getElementById('savedsearch-selector');
  var queryInput = document.querySelector('textarea[name="query"]');
  if (selector && queryInput) {
    selector.addEventListener('change', function() {
      if (this.value) {
        queryInput.value = this.value;
      }
    });
  }
});
