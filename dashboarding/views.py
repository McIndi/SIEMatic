from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import JsonResponse
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .utils import format_kwargs_spec
from .forms import DashboardForm, PanelFormSet, DashboardParamsForm
from .models import Dashboard, Panel
from search2.engine.core import PIPELINE_BUILTIN_FIELDS, run_pipeline
from search2.utils import coerce_to_list_of_dicts
import logging
import json

logger = logging.getLogger(__name__)

@login_required
def dashboard_list(request):
    dashboards = Dashboard.objects.filter(created_by=request.user)
    return render(request, 'dashboarding/dashboard_list.html', {'dashboards': dashboards})

@login_required
def dashboard_create(request):
    logger.info("Dashboarding: dashboard_create called")
    if request.method == 'POST':
        form = DashboardForm(request.POST)
        formset = PanelFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            dashboard = form.save(commit=False)
            dashboard.created_by = request.user
            dashboard.save()
            formset.instance = dashboard
            formset.save()
            return redirect('dashboarding:dashboard_detail', pk=dashboard.pk)
    else:
        form = DashboardForm()
        formset = PanelFormSet()
    return render(request, 'dashboarding/dashboard_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Dashboard'
    })

@login_required
def dashboard_edit(request, pk):
    dashboard = get_object_or_404(Dashboard.objects.prefetch_related('panels'), pk=pk, created_by=request.user)
    if request.method == 'POST':
        form = DashboardForm(request.POST, instance=dashboard)
        formset = PanelFormSet(request.POST, instance=dashboard)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect('dashboarding:dashboard_detail', pk=dashboard.pk)
    else:
        form = DashboardForm(instance=dashboard)
        formset = PanelFormSet(instance=dashboard)
    return render(request, 'dashboarding/dashboard_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit Dashboard'
    })

@login_required
def dashboard_detail(request, pk):
    dashboard = get_object_or_404(Dashboard.objects.prefetch_related('panels'), pk=pk, created_by=request.user)
    params_form = DashboardParamsForm(dashboard)
    if request.method == 'POST':
        params_form = DashboardParamsForm(dashboard, request.POST)
        if params_form.is_valid():
            # Process the form and run searches with params
            params = params_form.cleaned_data
            # Let the pipeline engine format both dashboard parameters and its
            # built-in time placeholders in one pass.
            panel_data = []
            for panel in dashboard.panels.all():
                search_query = panel.search
                if search_query:
                    try:
                        result = run_pipeline(
                            None,
                            search_query,
                            request=request,
                            environ=params,
                        )
                        result = coerce_to_list_of_dicts(result)
                        panel_data.append({
                            'panel': panel,
                            'data': result,
                        })
                    except Exception as e:
                        panel_data.append({
                            'panel': panel,
                            'error': str(e),
                        })
                else:
                    panel_data.append({
                        'panel': panel,
                        'data': None,
                    })
            return render(request, 'dashboarding/dashboard_view.html', {
                'dashboard': dashboard,
                'params_form': params_form,
                'panel_data': panel_data,
            })
    return render(request, 'dashboarding/dashboard_view.html', {
        'dashboard': dashboard,
        'params_form': params_form,
        'panel_data': None,
    })

@login_required
def dashboard_delete(request, pk):
    dashboard = get_object_or_404(Dashboard.objects.prefetch_related('panels'), pk=pk, created_by=request.user)
    if request.method == 'POST':
        dashboard.delete()
        return redirect('dashboarding:dashboard_list')
    return render(request, 'dashboarding/dashboard_confirm_delete.html', {'dashboard': dashboard})

@login_required
@require_http_methods(["POST"])
def panel_preview(request):
    search = request.POST.get('search', '')
    logger.info("Panel preview called with search: %s", search)
    visualization_type = request.POST.get('visualization_type', 'table')
    x_field = request.POST.get('x_field', '')
    y_field = request.POST.get('y_field', '')
    by_field = request.POST.get('by_field', '')
    chart_type = request.POST.get('chart_type', 'line')
    defaults_str = request.POST.get('defaults', '{}')
    logger.info("Received x_field: %s, y_field: %s, visualization_type: %s", x_field, y_field, visualization_type)
    
    if not search:
        return JsonResponse({'error': 'No search provided'})
    
    try:
        # Parse defaults
        try:
            defaults = json.loads(defaults_str) if defaults_str else {}
        except json.JSONDecodeError:
            defaults = {}
        
        # Detect placeholders and provide defaults
        specs = format_kwargs_spec(search)
        environ = {
            name: value
            for name, value in defaults.items()
            if name not in PIPELINE_BUILTIN_FIELDS
        }
        for name, field_type in specs.items():
            if name in PIPELINE_BUILTIN_FIELDS:
                continue
            if name not in environ:
                if field_type == int:
                    environ[name] = 10
                elif field_type == float:
                    environ[name] = 10.0
                else:
                    environ[name] = 'default'
        result = run_pipeline(None, search, request=request, environ=environ)
        data = coerce_to_list_of_dicts(result)
        return JsonResponse({
            'data': data,
            'visualization_type': visualization_type,
            'x_field': x_field,
            'y_field': y_field,
            'by_field': by_field,
            'chart_type': chart_type,
        })
    except Exception as e:
        logger.exception("Error in panel_preview: %s", e)
        return JsonResponse({'error': f'Error running search: {str(e)}'})
