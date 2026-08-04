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
