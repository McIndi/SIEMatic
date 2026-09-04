from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse

from dashboarding.forms import DashboardParamsForm
from dashboarding.models import Dashboard, Panel


class DashboardChartLabelTests(TestCase):
    def test_numeric_categories_are_not_passed_to_date_parser(self):
        source = get_template(
            'dashboarding/dashboard_view.html'
        ).template.source

        self.assertIn("typeof v !== 'string'", source)
        self.assertIn(r'/^\d{4}-\d{2}-\d{2}', source)


class PanelPreviewAuthTests(TestCase):
    def test_panel_preview_requires_login(self):
        response = self.client.post(
            reverse('dashboarding:panel_preview'),
            {'search': 'search index=default'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_panel_preview_passes_parameter_defaults_to_pipeline(self):
        user = get_user_model().objects.create_user(username="preview-user")
        self.client.force_login(user)

        with patch(
            "dashboarding.views.run_pipeline",
            return_value=[{"host": "workstation"}],
        ) as run_pipeline:
            response = self.client.post(
                reverse("dashboarding:panel_preview"),
                {
                    "search": "search --limit={limit:d}",
                    "defaults": '{"limit": 7}',
                },
            )

        self.assertEqual(response.status_code, 200)
        run_pipeline.assert_called_once()
        self.assertEqual(run_pipeline.call_args.kwargs["environ"]["limit"], 7)

    def test_panel_preview_leaves_builtin_time_placeholder_to_pipeline(self):
        user = get_user_model().objects.create_user(username="time-preview-user")
        self.client.force_login(user)

        with patch(
            "dashboarding.views.run_pipeline",
            return_value=[],
        ) as run_pipeline:
            response = self.client.post(
                reverse("dashboarding:panel_preview"),
                {
                    "search": "search --filter='created__gte={last_hour}'",
                    "defaults": '{"last_hour": "wrong"}',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("last_hour", run_pipeline.call_args.kwargs["environ"])


class DashboardParameterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dashboard-user")
        self.dashboard = Dashboard.objects.create(
            name="Time dashboard",
            created_by=self.user,
        )
        self.panel = Panel.objects.create(
            dashboard=self.dashboard,
            search=(
                "search --filter='created__gte={last_hour}' "
                "--limit={row_count:d}"
            ),
        )

    def test_parameter_form_excludes_pipeline_builtin_fields(self):
        form = DashboardParamsForm(self.dashboard)

        self.assertNotIn("last_hour", form.fields)
        self.assertIn("row_count", form.fields)

    def test_dashboard_passes_query_and_parameters_to_pipeline(self):
        self.client.force_login(self.user)

        with patch(
            "dashboarding.views.run_pipeline",
            return_value=[],
        ) as run_pipeline:
            response = self.client.post(
                reverse("dashboarding:dashboard_detail", args=[self.dashboard.pk]),
                {"row_count": "25"},
            )

        self.assertEqual(response.status_code, 200)
        run_pipeline.assert_called_once_with(
            None,
            self.panel.search,
            request=ANY,
            environ={"row_count": 25},
        )


class DashboardRefreshControlTests(TestCase):
    """The auto-refresh dropdown and the GET rendering it depends on."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='presenter', password='presenter-pw'
        )
        self.client.force_login(self.user)
        self.dashboard = Dashboard.objects.create(
            name='Audit', created_by=self.user, defaults={}
        )
        Panel.objects.create(
            dashboard=self.dashboard, title='Events', search='search index=default'
        )
        self.url = reverse(
            'dashboarding:dashboard_detail', kwargs={'pk': self.dashboard.pk}
        )

    def test_get_renders_panel_data_without_submitting_the_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['panel_data'])
        self.assertEqual(len(response.context['panel_data']), 1)

    def test_dropdown_offers_the_four_intervals(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.context['refresh_choices'],
            [(0, 'None'), (60, '1 minute'), (300, '5 minutes'), (600, '10 minutes')],
        )

    def test_default_is_no_refresh(self):
        response = self.client.get(self.url)

        self.assertEqual(response.context['refresh_seconds'], 0)

    def test_submitting_an_interval_persists_it(self):
        self.client.post(self.url, {'refresh_seconds': '300'})

        self.dashboard.refresh_from_db()
        self.assertEqual(self.dashboard.defaults['refresh_seconds'], 300)
        self.assertEqual(self.client.get(self.url).context['refresh_seconds'], 300)

    def test_an_interval_outside_the_choices_is_ignored(self):
        self.client.post(self.url, {'refresh_seconds': '5'})

        self.dashboard.refresh_from_db()
        self.assertNotIn('refresh_seconds', self.dashboard.defaults)

    def test_a_non_numeric_interval_is_ignored(self):
        self.dashboard.defaults = {'refresh_seconds': 60}
        self.dashboard.save()

        self.client.post(self.url, {'refresh_seconds': 'every-so-often'})

        self.dashboard.refresh_from_db()
        self.assertEqual(self.dashboard.defaults['refresh_seconds'], 60)

    def test_a_corrupt_stored_value_reads_as_off(self):
        self.dashboard.defaults = {'refresh_seconds': 'nonsense'}
        self.dashboard.save()

        self.assertEqual(self.client.get(self.url).context['refresh_seconds'], 0)

    def test_saving_the_interval_does_not_discard_other_defaults(self):
        self.dashboard.defaults = {'threshold': 5}
        self.dashboard.save()

        self.client.post(self.url, {'refresh_seconds': '60'})

        self.dashboard.refresh_from_db()
        self.assertEqual(
            self.dashboard.defaults, {'threshold': 5, 'refresh_seconds': 60}
        )

    def test_another_user_cannot_reach_the_dashboard(self):
        get_user_model().objects.create_user(username='other', password='other-pw')
        self.client.force_login(get_user_model().objects.get(username='other'))

        self.assertEqual(self.client.get(self.url).status_code, 404)


class DashboardDataEndpointTests(TestCase):
    """The JSON endpoint the auto-refresh uses to update panels in place."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='viewer', password='viewer-pw'
        )
        self.client.force_login(self.user)
        self.dashboard = Dashboard.objects.create(
            name='Audit', created_by=self.user, defaults={}
        )
        self.panel = Panel.objects.create(
            dashboard=self.dashboard,
            title='Events',
            search='search index=default',
            visualization_type='table',
        )
        self.url = reverse(
            'dashboarding:dashboard_data', kwargs={'pk': self.dashboard.pk}
        )

    def test_requires_login(self):
        self.client.logout()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)

    def test_rejects_get(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_returns_one_entry_per_panel_with_rows(self):
        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.return_value = [{'host': 'gw-1', 'count': 4}]
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['panels']), 1)
        panel = payload['panels'][0]
        self.assertEqual(panel['id'], self.panel.id)
        self.assertEqual(panel['visualization_type'], 'table')
        self.assertEqual(panel['data'], [{'host': 'gw-1', 'count': 4}])
        self.assertIsNone(panel['error'])

    def test_a_failing_panel_reports_its_error_without_failing_the_request(self):
        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.side_effect = ValueError('bad pipeline')
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['panels'][0]['error'], 'bad pipeline')

    def test_it_persists_the_refresh_interval(self):
        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.return_value = []
            response = self.client.post(self.url, {'refresh_seconds': '300'})

        self.dashboard.refresh_from_db()
        self.assertEqual(self.dashboard.defaults['refresh_seconds'], 300)
        self.assertEqual(response.json()['refresh_seconds'], 300)

    def test_another_user_cannot_read_the_data(self):
        get_user_model().objects.create_user(
            username='intruder', password='intruder-pw'
        )
        self.client.force_login(get_user_model().objects.get(username='intruder'))

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)


class SharedDashboardTests(TestCase):
    """Sharing widens who can read a dashboard, not who can change it."""

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='owner-pw')
        self.other = User.objects.create_user(username='other', password='other-pw')
        self.private = Dashboard.objects.create(
            name='Private', created_by=self.owner, defaults={}
        )
        self.shared = Dashboard.objects.create(
            name='Shared', created_by=self.owner, defaults={}, shared=True
        )
        Panel.objects.create(
            dashboard=self.shared, title='Events', search='search index=default'
        )
        self.client.force_login(self.other)

    def test_dashboards_default_to_private(self):
        self.assertFalse(self.private.shared)

    def test_the_list_shows_shared_dashboards_from_other_users(self):
        response = self.client.get(reverse('dashboarding:dashboard_list'))

        names = [d.name for d in response.context['dashboards']]
        self.assertIn('Shared', names)
        self.assertNotIn('Private', names)

    def test_a_shared_dashboard_can_be_viewed(self):
        url = reverse('dashboarding:dashboard_detail', kwargs={'pk': self.shared.pk})

        self.assertEqual(self.client.get(url).status_code, 200)

    def test_a_private_dashboard_stays_hidden(self):
        url = reverse('dashboarding:dashboard_detail', kwargs={'pk': self.private.pk})

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_data_endpoint_follows_the_same_rule(self):
        shared = reverse('dashboarding:dashboard_data', kwargs={'pk': self.shared.pk})
        private = reverse('dashboarding:dashboard_data', kwargs={'pk': self.private.pk})

        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.return_value = []
            self.assertEqual(self.client.post(shared).status_code, 200)
        self.assertEqual(self.client.post(private).status_code, 404)

    def test_a_viewer_cannot_edit_or_delete_a_shared_dashboard(self):
        pk = {'pk': self.shared.pk}

        self.assertEqual(
            self.client.get(reverse('dashboarding:dashboard_edit', kwargs=pk)).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('dashboarding:dashboard_delete', kwargs=pk)).status_code,
            404,
        )

    def test_a_viewer_does_not_overwrite_the_owners_refresh_interval(self):
        self.shared.defaults['refresh_seconds'] = 60
        self.shared.save(update_fields=['defaults'])
        url = reverse('dashboarding:dashboard_data', kwargs={'pk': self.shared.pk})

        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.return_value = []
            response = self.client.post(url, {'refresh_seconds': '600'})

        self.shared.refresh_from_db()
        self.assertEqual(self.shared.defaults['refresh_seconds'], 60)
        # The viewer's own session still honours the choice they made.
        self.assertEqual(response.json()['refresh_seconds'], 600)

    def test_the_owner_still_saves_the_interval(self):
        self.client.force_login(self.owner)
        url = reverse('dashboarding:dashboard_data', kwargs={'pk': self.shared.pk})

        with patch('dashboarding.views.run_pipeline') as run_pipeline:
            run_pipeline.return_value = []
            self.client.post(url, {'refresh_seconds': '600'})

        self.shared.refresh_from_db()
        self.assertEqual(self.shared.defaults['refresh_seconds'], 600)
