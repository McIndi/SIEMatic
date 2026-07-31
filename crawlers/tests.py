from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import Event

from .forms import FindingTriageForm
from .models import Finding
from .alerting.email_alert import EmailAlert
from .plugins.always_finding_crawler import AlwaysFindingCrawler
from .plugins.data_retention_crawler import DataRetentionCrawler


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


class CrawlerBehaviorTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            host="target",
            sourcetype="json",
            data='{"message": "test"}',
        )

    def test_crawler_creates_finding_and_honors_realert_cooldown(self):
        crawler = AlwaysFindingCrawler({"realert_cooldown": 300})

        crawler.run()
        crawler.run()

        self.assertEqual(Finding.objects.count(), 1)
        finding = Finding.objects.get()
        self.assertEqual(finding.event, self.event)
        self.assertEqual(finding.rule_name, "always_finding_test")

    def test_retention_deletes_only_old_matching_rows(self):
        old_match = self.event
        old_other = Event.objects.create(host="keep", data="old")
        recent_match = Event.objects.create(host="target", data="recent")
        old_time = timezone.now() - timedelta(days=31)
        Event.objects.filter(pk__in=[old_match.pk, old_other.pk]).update(
            created=old_time,
        )

        crawler = DataRetentionCrawler({
            "retention_days": 30,
            "rules": [{
                "split_by": "host",
                "allow": ["target"],
                "deny": [],
            }],
        })
        crawler.run()

        self.assertFalse(Event.objects.filter(pk=old_match.pk).exists())
        self.assertTrue(Event.objects.filter(pk=old_other.pk).exists())
        self.assertTrue(Event.objects.filter(pk=recent_match.pk).exists())

    def test_retention_preserves_events_with_actionable_findings(self):
        old_time = timezone.now() - timedelta(days=31)
        events = []
        for status in Finding.actionable_statuses():
            event = Event.objects.create(host="target", data=status)
            Event.objects.filter(pk=event.pk).update(created=old_time)
            Finding.objects.create(
                event=event,
                rule_name=f"{status} finding",
                description="This finding requires action.",
                status=status,
            )
            events.append(event)

        DataRetentionCrawler({
            "retention_days": 30,
            "rules": [{}],
        }).run()

        self.assertEqual(
            Event.objects.filter(pk__in=[event.pk for event in events]).count(),
            len(events),
        )
        self.assertEqual(Finding.objects.count(), len(events))

    def test_retention_deletes_old_events_with_only_terminal_findings(self):
        old_time = timezone.now() - timedelta(days=31)
        events = []
        for status in (Finding.Status.RESOLVED, Finding.Status.FALSE_POSITIVE):
            event = Event.objects.create(host="target", data=status)
            Event.objects.filter(pk=event.pk).update(created=old_time)
            Finding.objects.create(
                event=event,
                rule_name=f"{status} finding",
                description="This finding does not require action.",
                status=status,
            )
            events.append(event)

        with self.assertLogs(
            "crawlers.plugins.data_retention_crawler",
            level="INFO",
        ) as logs:
            DataRetentionCrawler({
                "retention_days": 30,
                "rules": [{}],
            }).run()

        self.assertFalse(
            Event.objects.filter(pk__in=[event.pk for event in events]).exists(),
        )
        self.assertFalse(Finding.objects.exists())
        self.assertTrue(any(
            "Total deleted: 2 events and 2 findings" in message
            for message in logs.output
        ))

    def test_retention_preserves_mixed_status_event(self):
        old_time = timezone.now() - timedelta(days=31)
        Event.objects.filter(pk=self.event.pk).update(created=old_time)
        Finding.objects.create(
            event=self.event,
            rule_name="Resolved finding",
            description="This finding is resolved.",
            status=Finding.Status.RESOLVED,
        )
        Finding.objects.create(
            event=self.event,
            rule_name="Active finding",
            description="This finding requires action.",
            status=Finding.Status.IN_PROGRESS,
        )

        DataRetentionCrawler({
            "retention_days": 30,
            "rules": [{}],
        }).run()

        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())
        self.assertEqual(Finding.objects.filter(event=self.event).count(), 2)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="siematic@example.test",
    )
    def test_email_alert_uses_django_email_backend(self):
        finding = Finding.objects.create(
            event=self.event,
            rule_name="Suspicious process",
            description="A suspicious process started.",
            severity="high",
        )

        EmailAlert({"recipients": ["soc@example.test"]}).send_alert(finding)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["soc@example.test"])
        self.assertIn("Suspicious process", mail.outbox[0].subject)
