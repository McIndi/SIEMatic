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
