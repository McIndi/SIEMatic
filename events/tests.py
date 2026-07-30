
"""
Tests for the events app.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Event
from .serializers import EventBulkSerializer


class EventExtractionTests(TestCase):
    def test_single_create_extracts_json_with_one_write(self):
        with self.assertNumQueries(1):
            event = Event.objects.create(
                sourcetype='json',
                data='{"message":"single","severity":3}',
            )

        self.assertEqual(
            event.extracted_fields,
            {'message': 'single', 'severity': 3},
        )
        self.assertEqual(
            Event.objects.get(pk=event.pk).extracted_fields,
            {'message': 'single', 'severity': 3},
        )

    def test_bulk_create_extracts_every_event_with_one_write(self):
        serializer = EventBulkSerializer(
            data=[
                {'sourcetype': 'json', 'data': '{"message":"first"}'},
                {'sourcetype': 'json', 'data': '{"message":"second"}'},
            ],
            many=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.assertNumQueries(1):
            events = serializer.save()

        self.assertEqual(
            [event.extracted_fields for event in events],
            [{'message': 'first'}, {'message': 'second'}],
        )
        self.assertEqual(
            list(
                Event.objects.order_by('id').values_list(
                    'extracted_fields', flat=True
                )
            ),
            [{'message': 'first'}, {'message': 'second'}],
        )

    def test_extractor_failure_does_not_prevent_insert(self):
        event = Event.objects.create(sourcetype='json', data='{malformed')

        self.assertIsNotNone(event.pk)
        self.assertEqual(event.extracted_fields, {})


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
