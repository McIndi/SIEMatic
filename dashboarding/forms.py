from django import forms
from django.forms import inlineformset_factory, modelformset_factory
from .models import Dashboard, Panel
from search2.engine.core import PIPELINE_BUILTIN_FIELDS

class PanelForm(forms.ModelForm):
    class Meta:
        model = Panel
        fields = ['search', 'visualization_type', 'chart_type', 'x_field', 'y_field', 'by_field', 'title', 'order']
        widgets = {
            'search': forms.Textarea(attrs={'rows': 3}),
        }

class DashboardForm(forms.ModelForm):
    class Meta:
        model = Dashboard
        fields = ['name', 'description', 'defaults']

# Inline formset for Panels in Dashboard
PanelFormSet = inlineformset_factory(
    Dashboard,
    Panel,
    form=PanelForm,
    extra=1,  # Allow adding new panels
    can_delete=True,
    can_order=True,
)

# Dynamic form for dashboard parameters
class DashboardParamsForm(forms.Form):
    """
    Dynamic form that adds fields based on placeholders in panel searches.
    """
    def __init__(self, dashboard, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import format_kwargs_spec

        # Collect all unique placeholders from all panels' searches
        placeholders = {}
        for panel in dashboard.panels.all():
            if panel.search:
                specs = format_kwargs_spec(panel.search)
                specs = {
                    name: field_type
                    for name, field_type in specs.items()
                    if name not in PIPELINE_BUILTIN_FIELDS
                }
                placeholders.update(specs)

        # Add fields to the form and set initial values from dashboard defaults
        for name, field_type in placeholders.items():
            if field_type == int:
                self.fields[name] = forms.IntegerField(required=False, initial=dashboard.defaults.get(name))
            elif field_type == float:
                self.fields[name] = forms.FloatField(required=False, initial=dashboard.defaults.get(name))
            else:
                self.fields[name] = forms.CharField(required=False, initial=dashboard.defaults.get(name))
