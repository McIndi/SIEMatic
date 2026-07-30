from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
