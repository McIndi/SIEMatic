from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import FindingBulkStatusForm, FindingFilterForm, FindingTriageForm
from .models import Finding


@login_required
@permission_required('crawlers.view_finding', raise_exception=True)
def finding_list(request):
    findings = Finding.objects.select_related('event', 'assignee')
    filter_form = FindingFilterForm(request.GET)

    if filter_form.is_valid():
        filters = filter_form.cleaned_data
        if filters['severity']:
            findings = findings.filter(severity=filters['severity'])
        if filters['status']:
            findings = findings.filter(status=filters['status'])
        if filters['rule_name']:
            findings = findings.filter(rule_name__icontains=filters['rule_name'])
        if filters['date_from']:
            findings = findings.filter(created_at__date__gte=filters['date_from'])
        if filters['date_to']:
            findings = findings.filter(created_at__date__lte=filters['date_to'])

    return render(request, 'crawlers/finding_list.html', {
        'findings': findings,
        'filter_form': filter_form,
        'finding_status_choices': Finding.Status.choices,
    })


@login_required
@permission_required('crawlers.view_finding', raise_exception=True)
def finding_detail(request, pk):
    finding = get_object_or_404(
        Finding.objects.select_related('event', 'assignee'),
        pk=pk,
    )
    triage_form = FindingTriageForm(instance=finding)
    return render(request, 'crawlers/finding_detail.html', {
        'finding': finding,
        'triage_form': triage_form,
    })


@login_required
@permission_required('crawlers.view_finding', raise_exception=True)
@permission_required('crawlers.change_finding', raise_exception=True)
@require_http_methods(['POST'])
def finding_update(request, pk):
    finding = get_object_or_404(Finding, pk=pk)
    form = FindingTriageForm(request.POST, instance=finding)
    if form.is_valid():
        form.save()
        messages.success(request, 'Finding triage details updated.')
    else:
        messages.error(request, 'Unable to update the finding. Check the form errors below.')
        return render(request, 'crawlers/finding_detail.html', {
            'finding': finding,
            'triage_form': form,
        }, status=400)
    return redirect('crawlers:finding_detail', pk=finding.pk)


@login_required
@permission_required('crawlers.view_finding', raise_exception=True)
@permission_required('crawlers.change_finding', raise_exception=True)
@require_POST
def finding_bulk_update(request):
    form = FindingBulkStatusForm(request.POST)
    if form.is_valid():
        findings = form.cleaned_data['finding_ids']
        updated = findings.update(
            status=form.cleaned_data['status'],
            updated_at=timezone.now(),
        )
        messages.success(request, f'Updated {updated} finding(s).')
    else:
        messages.error(request, 'Select at least one finding and a valid status.')
    return redirect('crawlers:finding_list')


@login_required
@permission_required('crawlers.view_finding', raise_exception=True)
@staff_member_required
def finding_delete(request, pk):
    finding = get_object_or_404(Finding, pk=pk)
    if request.method == 'POST':
        finding.delete()
        messages.success(request, 'Finding deleted.')
        return redirect('crawlers:finding_list')
    return render(request, 'crawlers/finding_confirm_delete.html', {'finding': finding})
