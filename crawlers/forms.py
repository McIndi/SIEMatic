from django import forms
from django.contrib.auth import get_user_model

from .models import Finding


class FindingFilterForm(forms.Form):
    severity = forms.ChoiceField(
        choices=[('', 'All severities'), *Finding._meta.get_field('severity').choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    status = forms.ChoiceField(
        choices=[('', 'All statuses'), *Finding.Status.choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    rule_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError('The start date must be on or before the end date.')
        return cleaned_data


class FindingTriageForm(forms.ModelForm):
    class Meta:
        model = Finding
        fields = ('status', 'assignee', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = get_user_model().objects.filter(
            is_active=True,
        ).order_by('username')


class FindingBulkStatusForm(forms.Form):
    finding_ids = forms.ModelMultipleChoiceField(
        queryset=Finding.objects.none(),
        widget=forms.MultipleHiddenInput,
    )
    status = forms.ChoiceField(choices=Finding.Status.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['finding_ids'].queryset = Finding.objects.all()
