
"""
Tests for the events app.
"""
import json

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


class LogfmtExtractionTests(TestCase):
    """Cover the logfmt sourcetype used by Go services on the mesh."""

    def test_quoted_value_keeps_its_spaces(self):
        event = Event.objects.create(
            sourcetype='logfmt',
            data='time=2026-09-02T17:21:19.585Z level=INFO msg="pipeline: response frame cancelled" plugin=ibac',
        )

        self.assertEqual(
            event.extracted_fields,
            {
                'time': '2026-09-02T17:21:19.585Z',
                'level': 'INFO',
                'msg': 'pipeline: response frame cancelled',
                'plugin': 'ibac',
            },
        )

    def test_sourcetype_match_is_case_insensitive(self):
        event = Event.objects.create(sourcetype='LogFmt', data='level=WARN')

        self.assertEqual(event.extracted_fields, {'level': 'WARN'})

    def test_bare_tokens_are_skipped(self):
        event = Event.objects.create(
            sourcetype='logfmt',
            data='starting level=INFO ready',
        )

        self.assertEqual(event.extracted_fields, {'level': 'INFO'})

    def test_value_containing_an_equals_sign_is_kept_whole(self):
        event = Event.objects.create(
            sourcetype='logfmt',
            data='url="https://example.test/?a=1&b=2" code=200',
        )

        self.assertEqual(
            event.extracted_fields,
            {'url': 'https://example.test/?a=1&b=2', 'code': '200'},
        )

    def test_unbalanced_quote_still_yields_the_fields_before_it(self):
        event = Event.objects.create(
            sourcetype='logfmt',
            data='level=ERROR msg="unterminated',
        )

        self.assertEqual(event.extracted_fields['level'], 'ERROR')

    def test_json_sourcetype_is_not_parsed_as_logfmt(self):
        event = Event.objects.create(
            sourcetype='json',
            data='{"message":"hello world"}',
        )

        self.assertEqual(event.extracted_fields, {'message': 'hello world'})


class ObjectEventDataTests(TestCase):
    """A shipper should be able to post an object without encoding it first."""

    def setUp(self):
        user = get_user_model().objects.create_user(username='shipper', password='shipper-pw')
        user.groups.add(Group.objects.get(name='Agent'))
        self.client = APIClient()
        self.client.force_authenticate(user=user)

    def test_object_data_is_encoded_and_extracted(self):
        response = self.client.post(
            reverse('event-list'),
            {'sourcetype': 'json', 'data': {'message': 'hello', 'severity': 3}},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        event = Event.objects.get()
        self.assertEqual(json.loads(event.data), {'message': 'hello', 'severity': 3})
        self.assertEqual(event.extracted_fields, {'message': 'hello', 'severity': 3})

    def test_string_data_is_stored_unchanged(self):
        raw = 'time=2026-09-02T17:21:19.585Z level=INFO plugin=ibac'
        response = self.client.post(
            reverse('event-list'),
            {'sourcetype': 'logfmt', 'data': raw},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        event = Event.objects.get()
        self.assertEqual(event.data, raw)
        self.assertEqual(event.extracted_fields['plugin'], 'ibac')

    def test_list_data_is_encoded(self):
        response = self.client.post(
            reverse('event-list'),
            {'sourcetype': 'default', 'data': [1, 2, 3]},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(json.loads(Event.objects.get().data), [1, 2, 3])

    def test_bulk_post_accepts_both_shapes(self):
        response = self.client.post(
            reverse('event-list'),
            [
                {'sourcetype': 'json', 'data': {'message': 'object'}},
                {'sourcetype': 'json', 'data': '{"message":"string"}'},
            ],
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            list(Event.objects.order_by('id').values_list('extracted_fields', flat=True)),
            [{'message': 'object'}, {'message': 'string'}],
        )
