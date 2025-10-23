

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import SavedSearch

class SavedSearchForm(forms.ModelForm):
    class Meta:
        model = SavedSearch
        fields = ['name', 'query']

class SearchDashboardForm(forms.Form):
    query = forms.CharField(label='Search Query', required=True, widget=forms.Textarea)
    enable_summary = forms.BooleanField(label='Enable Summary Stats', required=False, initial=False)

class ChartForm(forms.Form):
    x_field = forms.CharField(label="X Field", required=True)
    y_field = forms.CharField(label="Y Field", required=True)
    chart_type = forms.ChoiceField(
        label="Chart Type",
        choices=[
            ("bar", "Bar"),
            ("line", "Line"),
            ("pie", "Pie"),
        ],
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Render Chart'))

