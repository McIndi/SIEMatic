class SavedSearchSelectorComponent:
    template_name = "components/search2/savedsearch_selector.html"

    class Media:
        js = ["search2/savedsearch_selector.js"]

    def get_context_data(self, saved_searches=None, **kwargs):
        return {
            "saved_searches": saved_searches or [],
        }
