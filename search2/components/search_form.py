from search2.forms import SearchDashboardForm

class SearchFormComponent:
    template_name = "components/search2/search_form.html"

    def get_context_data(self, form=None, **kwargs):
        if form is None:
            form = SearchDashboardForm()
        return {"form": form}

# Optionally, you can add methods for handling POST, etc., if needed.