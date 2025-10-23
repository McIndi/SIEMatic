from search2.utils import extract_field_names

class ChartComponent:
    template_name = "components/search2/chart.html"

    class Media:
        js = ["search2/chart.js"]

    def get_context_data(self, results=None, x_field=None, y_field=None, chart_type=None, chart_form=None, **kwargs):
        # Extract available field names from results for dropdowns
        available_fields = extract_field_names(results) if results else []
        
        return {
            "results": results,
            "available_fields": available_fields,
            "x_field": x_field,
            "y_field": y_field,
            "chart_type": chart_type,
            "chart_form": chart_form,
        }
