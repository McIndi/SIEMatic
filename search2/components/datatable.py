class DatatableComponent:
    template_name = "components/search2/datatable.html"

    class Media:
        js = ["search2/datatable.js"]

    def get_context_data(self, results=None, **kwargs):
        return {
            "results": results,
        }
