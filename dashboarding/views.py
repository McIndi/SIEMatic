from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.db.models import Q
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

# Auto-refresh intervals offered on a dashboard, in seconds. Zero is off.
REFRESH_CHOICES = [
    (0, 'None'),
    (60, '1 minute'),
    (300, '5 minutes'),
    (600, '10 minutes'),
]
REFRESH_KEY = 'refresh_seconds'
VALID_REFRESH_SECONDS = {value for value, _ in REFRESH_CHOICES}


def stored_refresh_seconds(dashboard):
    """
    Read the saved auto-refresh interval, ignoring anything unexpected.

    Args:
        dashboard: The Dashboard whose defaults hold the interval.

    Returns:
        int: One of REFRESH_CHOICES, or 0 when nothing valid is stored.
    """
    try:
        value = int(dashboard.defaults.get(REFRESH_KEY, 0))
    except (AttributeError, TypeError, ValueError):
        return 0
    return value if value in VALID_REFRESH_SECONDS else 0


def save_refresh_seconds(dashboard, raw):
    """
    Persist a submitted auto-refresh interval in the dashboard defaults.

    ``defaults`` is already a JSONField, so this needs no migration.

    Args:
        dashboard: The Dashboard to update.
        raw: The submitted value, or None when the field was not sent.

    Returns:
        int: The interval now in effect.
    """
    if raw is None:
        return stored_refresh_seconds(dashboard)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return stored_refresh_seconds(dashboard)
    if value not in VALID_REFRESH_SECONDS:
        return stored_refresh_seconds(dashboard)
    if dashboard.defaults.get(REFRESH_KEY) != value:
        dashboard.defaults[REFRESH_KEY] = value
        dashboard.save(update_fields=['defaults', 'updated_at'])
    return value


def visible_dashboards(user):
    """
    Return the dashboards a user may view: their own, plus anything shared.

    Args:
        user: The signed-in user.

    Returns:
        QuerySet: Dashboards the user is allowed to read.
    """
    return Dashboard.objects.filter(Q(created_by=user) | Q(shared=True))


def apply_refresh_seconds(dashboard, raw, user):
    """
    Work out the interval to use, saving it only for the dashboard's owner.

    Someone viewing a shared dashboard can change the interval for their own
    session, but must not write a new default onto a dashboard they do not own.

    Args:
        dashboard: The Dashboard being viewed.
        raw: The submitted value, or None when the field was not sent.
        user: The signed-in user.

    Returns:
        int: The interval now in effect.
    """
    if dashboard.created_by_id == user.pk:
        return save_refresh_seconds(dashboard, raw)
    if raw is None:
        return stored_refresh_seconds(dashboard)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return stored_refresh_seconds(dashboard)
    return value if value in VALID_REFRESH_SECONDS else stored_refresh_seconds(dashboard)


def build_panel_data(dashboard, params, request):
    """
    Run every panel's search and collect the rows for rendering.

    Args:
        dashboard: The Dashboard whose panels to run.
        params: Placeholder values passed to the pipeline engine.
        request: The HTTP request, used for authorization inside the pipeline.

    Returns:
        list: One dict per panel, carrying either 'data' or 'error'.
    """
    panel_data = []
    for panel in dashboard.panels.all():
        if not panel.search:
            panel_data.append({'panel': panel, 'data': None})
            continue
        try:
            result = run_pipeline(
                None,
                panel.search,
                request=request,
                environ=params,
            )
            panel_data.append({
                'panel': panel,
                'data': coerce_to_list_of_dicts(result),
            })
        except Exception as e:
            panel_data.append({'panel': panel, 'error': str(e)})
    return panel_data


@login_required
def dashboard_list(request):
    dashboards = visible_dashboards(request.user)
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
    dashboard = get_object_or_404(
        visible_dashboards(request.user).prefetch_related('panels'), pk=pk
    )
    panel_data = None
    if request.method == 'POST':
        params_form = DashboardParamsForm(dashboard, request.POST)
        refresh_seconds = apply_refresh_seconds(
            dashboard, request.POST.get(REFRESH_KEY), request.user
        )
        if params_form.is_valid():
            # Let the pipeline engine format both dashboard parameters and its
            # built-in time placeholders in one pass.
            panel_data = build_panel_data(dashboard, params_form.cleaned_data, request)
    else:
        params_form = DashboardParamsForm(dashboard)
        refresh_seconds = stored_refresh_seconds(dashboard)
        # Run the panels on GET as well. Auto-refresh reloads the page, and a
        # dashboard that renders empty until someone presses a button is not a
        # dashboard.
        params = {name: dashboard.defaults.get(name) for name in params_form.fields}
        panel_data = build_panel_data(dashboard, params, request)
    return render(request, 'dashboarding/dashboard_view.html', {
        'dashboard': dashboard,
        'params_form': params_form,
        'panel_data': panel_data,
        'refresh_seconds': refresh_seconds,
        'refresh_choices': REFRESH_CHOICES,
    })

@login_required
@require_http_methods(["POST"])
def dashboard_data(request, pk):
    """
    Return every panel's rows as JSON so the page can update without reloading.

    Takes the same form fields as ``dashboard_detail`` so the caller can post
    the params form unchanged, and persists the auto-refresh choice the same
    way, which lets the dropdown save itself without a page load.

    Args:
        request: The HTTP request carrying the params form.
        pk: Primary key of the dashboard.

    Returns:
        JsonResponse: Panels with their rows, or 400 with form errors.
    """
    dashboard = get_object_or_404(
        visible_dashboards(request.user).prefetch_related('panels'), pk=pk
    )
    params_form = DashboardParamsForm(dashboard, request.POST)
    refresh_seconds = apply_refresh_seconds(
        dashboard, request.POST.get(REFRESH_KEY), request.user
    )
    if not params_form.is_valid():
        return JsonResponse({'errors': params_form.errors}, status=400)

    panels = []
    for item in build_panel_data(dashboard, params_form.cleaned_data, request):
        panel = item['panel']
        panels.append({
            'id': panel.id,
            'title': panel.title,
            'visualization_type': panel.visualization_type,
            'x_field': panel.x_field,
            'y_field': panel.y_field,
            'by_field': panel.by_field,
            'chart_type': panel.chart_type,
            'data': item.get('data'),
            'error': item.get('error'),
        })
    return JsonResponse({'panels': panels, 'refresh_seconds': refresh_seconds})


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
