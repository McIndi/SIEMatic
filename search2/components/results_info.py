from search2.utils import calculate_results_summary

class ResultsInfoComponent:
    template_name = "components/search2/results_info.html"

    def get_context_data(self, results=None, **kwargs):
        summary = calculate_results_summary(results) if results is not None else None
        return {
            "summary": summary,
            "results": results,
        }
