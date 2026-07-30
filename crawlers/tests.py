from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event

from .forms import FindingTriageForm
from .models import Finding


class FindingTriageViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            index='security',
            sourcetype='json',
            source='test',
            host='workstation-1',
            data='{"message": "failed login"}',
            extracted_fields={'username': 'analyst'},
        )
        cls.finding = Finding.objects.create(
            event=cls.event,
            rule_name='Repeated failed login',
            description='Several failed logins were observed.',
            severity='high',
            mitre_tactic='Credential Access',
            mitre_technique='Brute Force',
        )
        cls.other_finding = Finding.objects.create(
            event=cls.event,
            rule_name='Benign test',
            description='A low severity test.',
            severity='low',
            status=Finding.Status.RESOLVED,
        )
        cls.viewer = get_user_model().objects.create_user(
            username='viewer',
            password='test-password',
        )
        cls.viewer.groups.clear()
        cls.viewer.user_permissions.add(
            Permission.objects.get(codename='view_finding', content_type__app_label='crawlers'),
        )
        cls.editor = get_user_model().objects.create_user(
            username='editor',
            password='test-password',
        )
        cls.editor.groups.clear()
        cls.editor.user_permissions.add(
            *Permission.objects.filter(
                codename__in=('view_finding', 'change_finding'),
                content_type__app_label='crawlers',
            ),
        )
        cls.unprivileged = get_user_model().objects.create_user(
            username='unprivileged',
            password='test-password',
        )
        cls.unprivileged.groups.clear()
        cls.staff = get_user_model().objects.create_user(
            username='staff',
            password='test-password',
            is_staff=True,
        )
        cls.staff.groups.clear()
        cls.staff.user_permissions.add(
            Permission.objects.get(codename='view_finding', content_type__app_label='crawlers'),
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('crawlers:finding_list'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('crawlers:finding_list')}",
        )

    def test_user_without_view_permission_gets_forbidden(self):
        self.client.force_login(self.unprivileged)

        response = self.client.get(reverse('crawlers:finding_list'))

        self.assertEqual(response.status_code, 403)

    def test_viewer_can_list_and_inspect_finding_and_event(self):
        self.client.force_login(self.viewer)

        list_response = self.client.get(reverse('crawlers:finding_list'))
        detail_response = self.client.get(
            reverse('crawlers:finding_detail', args=(self.finding.pk,)),
        )

        self.assertContains(list_response, self.finding.rule_name)
        self.assertContains(detail_response, self.finding.description)
        self.assertContains(detail_response, 'Credential Access')
        self.assertContains(detail_response, 'failed login')
        self.assertContains(detail_response, 'username')

    def test_list_filters_by_severity_status_rule_and_date(self):
        self.client.force_login(self.viewer)
        today = timezone.localdate()

        response = self.client.get(reverse('crawlers:finding_list'), {
            'severity': 'high',
            'status': Finding.Status.NEW,
            'rule_name': 'failed',
            'date_from': today - timedelta(days=1),
            'date_to': today + timedelta(days=1),
        })

        self.assertContains(response, self.finding.rule_name)
        self.assertNotContains(response, self.other_finding.rule_name)

    def test_viewer_cannot_update_triage(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse('crawlers:finding_update', args=(self.finding.pk,)),
            {'status': Finding.Status.ACKNOWLEDGED, 'notes': 'Reviewed'},
        )

        self.assertEqual(response.status_code, 403)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, Finding.Status.NEW)

    def test_editor_can_only_update_triage_fields(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse('crawlers:finding_update', args=(self.finding.pk,)),
            {
                'status': Finding.Status.IN_PROGRESS,
                'assignee': self.editor.pk,
                'notes': 'Investigating this host.',
                'rule_name': 'Tampered rule',
                'severity': 'critical',
            },
        )

        self.assertRedirects(
            response,
            reverse('crawlers:finding_detail', args=(self.finding.pk,)),
        )
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, Finding.Status.IN_PROGRESS)
        self.assertEqual(self.finding.assignee, self.editor)
        self.assertEqual(self.finding.notes, 'Investigating this host.')
        self.assertEqual(self.finding.rule_name, 'Repeated failed login')
        self.assertEqual(self.finding.severity, 'high')

    def test_editor_can_bulk_update_status(self):
        self.client.force_login(self.editor)

        response = self.client.post(reverse('crawlers:finding_bulk_update'), {
            'finding_ids': [self.finding.pk, self.other_finding.pk],
            'status': Finding.Status.FALSE_POSITIVE,
        })

        self.assertRedirects(response, reverse('crawlers:finding_list'))
        self.assertEqual(
            Finding.objects.filter(status=Finding.Status.FALSE_POSITIVE).count(),
            2,
        )

    def test_non_staff_gets_forbidden_instead_of_admin_login_redirect(self):
        self.client.force_login(self.editor)
        denied = self.client.post(
            reverse('crawlers:finding_delete', args=(self.finding.pk,)),
        )
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn('Location', denied)
        self.assertTrue(Finding.objects.filter(pk=self.finding.pk).exists())

    def test_anonymous_delete_uses_application_login(self):
        delete_url = reverse('crawlers:finding_delete', args=(self.finding.pk,))

        response = self.client.get(delete_url)

        self.assertRedirects(response, f'{reverse("login")}?next={delete_url}')

    def test_staff_can_delete(self):
        self.client.force_login(self.staff)
        deleted = self.client.post(
            reverse('crawlers:finding_delete', args=(self.finding.pk,)),
        )
        self.assertRedirects(deleted, reverse('crawlers:finding_list'))
        self.assertFalse(Finding.objects.filter(pk=self.finding.pk).exists())


class FindingTriageFormTests(TestCase):
    def test_form_exposes_only_triage_fields(self):
        self.assertEqual(
            list(FindingTriageForm().fields),
            ['status', 'assignee', 'notes'],
        )
