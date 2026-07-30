
"""
Tests for the events app.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Event


class EventApiPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='eventuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.payload = {
            'index': 'default',
            'sourcetype': 'default',
            'source': 'api',
            'host': 'localhost',
            'data': '{"message":"hello"}',
        }

    def test_view_only_user_cannot_create_event(self):
        response = self.client.post(reverse('event-list'), self.payload, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Event.objects.count(), 0)

    def test_agent_group_user_can_create_event(self):
        self.user.groups.add(Group.objects.get(name='Agent'))

        response = self.client.post(reverse('event-list'), self.payload, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Event.objects.count(), 1)
