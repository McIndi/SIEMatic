import logging

from django.http import HttpResponseForbidden
from django.http import HttpResponseNotAllowed
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect

from .utils import coerce_to_list_of_dicts, extract_field_names, calculate_results_summary
from .apps import generate_command_help_rows
from .models import SavedSearch
from .forms import SavedSearchForm, SearchDashboardForm, ChartForm

logger = logging.getLogger(__name__)

@login_required
def savedsearch_list(request):
	"""
	Render a list of saved searches for the current user.
	"""
	logger = logging.getLogger(__name__)
	logger.info("Entered savedsearch_list view")
	searches = SavedSearch.objects.visible_to(request.user).order_by('name')
	logger.debug("Found %d saved searches for user %s", searches.count(), request.user)
	return render(request, 'search2/savedsearch_list.html', {'searches': searches})

@login_required
def savedsearch_create(request):
	"""
	Handle creation of a new saved search, including preview functionality.
	"""
	logger = logging.getLogger(__name__)
	logger.info("Entered savedsearch_create view")
	preview_data = None
	if request.method == 'POST':
		form = SavedSearchForm(request.POST)
		logger.debug("POST data: %s", request.POST)
		if 'preview' in request.POST and form.is_valid():
			query = form.cleaned_data['query']
			logger.info("Preview requested for query: %s", query)
			try:
				from search2.engine.core import run_pipeline
				results = run_pipeline(None, query, request=request)
				from .utils import coerce_to_list_of_dicts
				preview_data = coerce_to_list_of_dicts(results)
				logger.debug("Preview data: %s", preview_data)
			except Exception as e:
				preview_data = [{'error': str(e)}]
				logger.error("Error generating preview: %s", str(e))
		elif form.is_valid():
			saved_search = form.save(commit=False)
			saved_search.owner = request.user
			saved_search.save()
			form.save_m2m()
			logger.info("SavedSearch created for user %s with pk=%s", request.user, saved_search.pk)
			return redirect('savedsearch_list')
		else:
			logger.warning("SavedSearchForm invalid in savedsearch_create")
	else:
		form = SavedSearchForm()
	return render(request, 'search2/savedsearch_form.html', {'form': form, 'preview_data': preview_data, 'help_rows': generate_command_help_rows()})

@login_required
def savedsearch_update(request, pk):
	"""
	Handle update of an existing saved search, including preview functionality.
	"""
	logger = logging.getLogger(__name__)
	logger.info("Entered savedsearch_update view for pk=%s", pk)
	saved_search = get_object_or_404(SavedSearch, pk=pk, owner=request.user)
	preview_data = None
	if request.method == 'POST':
		form = SavedSearchForm(request.POST, instance=saved_search)
		logger.debug("POST data: %s", request.POST)
		if 'preview' in request.POST and form.is_valid():
			query = form.cleaned_data['query']
			logger.info("Preview requested for query: %s", query)
			try:
				from search2.engine.core import run_pipeline
				results = run_pipeline(None, query, request=request)
				from .utils import coerce_to_list_of_dicts
				preview_data = coerce_to_list_of_dicts(results)
				logger.debug("Preview data: %s", preview_data)
			except Exception as e:
				preview_data = [{'error': str(e)}]
				logger.error("Error generating preview: %s", str(e))
		elif form.is_valid():
			form.save()
			logger.info("SavedSearch updated for user %s with pk=%s", request.user, pk)
			return redirect('savedsearch_list')
		else:
			logger.warning("SavedSearchForm invalid in savedsearch_update")
	else:
		form = SavedSearchForm(instance=saved_search)
	return render(request, 'search2/savedsearch_form.html', {'form': form, 'preview_data': preview_data, 'help_rows': generate_command_help_rows()})

@login_required
def savedsearch_delete(request, pk):
	"""
	Handle deletion of a saved search.
	"""
	logger = logging.getLogger(__name__)
	logger.info("Entered savedsearch_delete view for pk=%s", pk)
	saved_search = get_object_or_404(SavedSearch, pk=pk, owner=request.user)
	if request.method == 'POST':
		saved_search.delete()
		logger.info("SavedSearch deleted for user %s with pk=%s", request.user, pk)
		return redirect('savedsearch_list')
	return render(request, 'search2/savedsearch_confirm_delete.html', {'object': saved_search})

@login_required
def dashboard(request):
	"""
	Render the dashboard view, handling search and chart forms, and displaying results.
	"""
	logger = logging.getLogger(__name__)
	logger.info("Dashboard view accessed with method: %s", request.method)
	if request.method == 'GET':
		form = SearchDashboardForm(request.GET or None)
	elif request.method == 'POST':
		form = SearchDashboardForm(request.POST or None)
	else:
		logger.error(f"Method {request.method} not allowed in dashboard view")
		return HttpResponseNotAllowed(['GET', 'POST'])
	chart_form = ChartForm(request.POST or None)
	if form.is_valid():
		query = form.cleaned_data.get("query", "")
		enable_summary = form.cleaned_data.get('enable_summary', False)
		logger.info("Dashboard form valid, query: %s", query)
		if not query.strip():
			results = [{"results": "No query provided"}]
			logger.warning("No query provided in dashboard view")
		else:
			try:
				from search2.engine.core import run_pipeline
				results = run_pipeline(None, query, request=request)
				logger.debug("run_pipeline returned results")
			except Exception as e:
				logger.error("Error occurred while running pipeline: %s", e)
				results = [{"results": "Error occurred while processing query", "error": str(e)}]
		coerced = coerce_to_list_of_dicts(results)
		if enable_summary:
			summary = calculate_results_summary(coerced)
		else:
			summary = None
		context = {
			'form': form,
			'chart_form': chart_form,
			'results': coerced,
			'available_fields': extract_field_names(coerced),
			'summary': summary,
			'help_rows': generate_command_help_rows(),
		}
	else:
		logger.warning("Dashboard form invalid: %s", form.errors)
		coerced_error = coerce_to_list_of_dicts([{"results": "Form is not valid, see errors above", "errors": form.errors}])
		context = {
			'form': form,
			'chart_form': chart_form,
			'results': coerced_error,
			'available_fields': extract_field_names(coerced_error),
			'summary': None,
			'help_rows': generate_command_help_rows(),
		}
	context['saved_searches'] = list(SavedSearch.objects.visible_to(request.user).order_by('name'))
	logger.info("Dashboard view rendering response")
	return render(request, 'search2/dashboard.html', context)
