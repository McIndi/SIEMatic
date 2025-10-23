class VisualizationSelectorComponent:
    class Media:
        js = ["search2/visualization_selector.js"]

    template_name = "components/search2/visualization_selector.html"

    def get_context_data(self, results=None, x_field=None, y_field=None, chart_type=None, chart_form=None, **kwargs):
        return {
            "results": results,
            "x_field": x_field,
            "y_field": y_field,
            "chart_type": chart_type,
            "chart_form": chart_form,
        }
