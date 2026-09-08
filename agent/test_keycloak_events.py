"""Contract tests for the checkpointed Keycloak event collector."""

from datetime import datetime, timezone
from queue import Queue
from threading import Event

from django.test import SimpleTestCase

from agent.plugins.keycloak_events_plugin import (
    KeycloakApiClient,
    KeycloakEventsPlugin,
    decode_cursor,
    encode_cursor,
    event_fingerprint,
)


class FakeKeycloakClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_events(
        self, realm, *, date_from, date_to, first, max_results
    ):
        self.calls.append((realm, date_from, date_to, first, max_results))
        return self.pages.get(first, [])


class KeycloakEventsPluginTests(SimpleTestCase):
    def make_plugin(self, client, **config):
        return KeycloakEventsPlugin(
            {
                'agent_id': 'shipper-keycloak-events',
                'hostname': 'keycloak-events-0',
                'version': '1.0',
                'realm': 'rossoctl',
                'index': 'keycloak',
                'source': 'keycloak/rossoctl',
                'poll_interval': 30,
                **config,
            },
            Queue(maxsize=10),
            Queue(maxsize=10),
            Event(),
            client=client,
        )

    def test_cursor_round_trip_and_canonical_fingerprint_fallback(self):
        cursor = {'timestamp': 1788883200123, 'fingerprints': ['one', 'two']}
        without_id_a = {'time': 1, 'type': 'LOGIN', 'details': {'b': 2, 'a': 1}}
        without_id_b = {'details': {'a': 1, 'b': 2}, 'type': 'LOGIN', 'time': 1}

        self.assertEqual(decode_cursor(encode_cursor(cursor)), cursor)
        self.assertEqual(event_fingerprint({'id': 'event-id'}), 'event-id')
        self.assertEqual(
            event_fingerprint(without_id_a),
            event_fingerprint(without_id_b),
        )

    def test_inclusive_boundary_skips_only_acknowledged_event_ids(self):
        boundary = 1788883200123
        client = FakeKeycloakClient({
            0: [
                {'id': 'later', 'time': boundary + 1, 'type': 'LOGOUT'},
                {'id': 'new-at-boundary', 'time': boundary, 'type': 'LOGIN'},
                {'id': 'already-seen', 'time': boundary, 'type': 'LOGIN'},
            ],
        })
        plugin = self.make_plugin(client)
        plugin.acknowledged_positions[plugin.target_id] = encode_cursor({
            'timestamp': boundary,
            'fingerprints': ['already-seen'],
        })

        batches = plugin.collect_once(
            timestamp=datetime.fromtimestamp((boundary + 1000) / 1000, timezone.utc)
        )

        self.assertEqual(
            [event['data']['id'] for event in batches[0]['events']],
            ['new-at-boundary', 'later'],
        )
        self.assertEqual(decode_cursor(batches[0]['cursor']), {
            'timestamp': boundary + 1,
            'fingerprints': ['later'],
        })

    def test_fetches_every_page_and_reorders_newest_first_api_results(self):
        client = FakeKeycloakClient({
            0: [
                {'id': 'three', 'time': 3, 'type': 'LOGIN'},
                {'id': 'two', 'time': 2, 'type': 'LOGIN'},
            ],
            2: [{'id': 'one', 'time': 1, 'type': 'LOGIN'}],
        })
        plugin = self.make_plugin(client, page_size=2)
        plugin.acknowledged_positions[plugin.target_id] = encode_cursor({
            'timestamp': 0,
            'fingerprints': [],
        })

        batches = plugin.collect_once(
            timestamp=datetime.fromtimestamp(10, timezone.utc)
        )

        self.assertEqual(
            [event['data']['id'] for event in batches[0]['events']],
            ['one', 'two', 'three'],
        )
        self.assertEqual([call[3] for call in client.calls], [0, 2])

    def test_unknown_target_starts_at_collection_time(self):
        client = FakeKeycloakClient({0: []})
        plugin = self.make_plugin(client)
        started = datetime(2026, 9, 8, 12, 0, 0, 123000, tzinfo=timezone.utc)

        self.assertEqual(plugin.collect_once(timestamp=started), [])

        self.assertEqual(client.calls[0][1], 1788868800123)
        self.assertEqual(client.calls[0][2], 1788868800123)

    def test_quiet_first_poll_does_not_skip_events_before_second_poll(self):
        client = FakeKeycloakClient({0: []})
        plugin = self.make_plugin(client)
        first_poll = datetime.fromtimestamp(1, timezone.utc)

        self.assertEqual(plugin.collect_once(timestamp=first_poll), [])
        client.pages[0] = [{'id': 'between', 'time': 1500, 'type': 'LOGIN'}]
        batches = plugin.collect_once(
            timestamp=datetime.fromtimestamp(2, timezone.utc)
        )

        self.assertEqual(batches[0]['events'][0]['data']['id'], 'between')
        self.assertEqual(client.calls[-1][1], 1000)

    def test_one_millisecond_boundary_is_not_split_between_batches(self):
        client = FakeKeycloakClient({
            0: [
                {'id': f'event-{number}', 'time': 1000, 'type': 'LOGIN'}
                for number in range(3)
            ],
        })
        plugin = self.make_plugin(client, batch_size=2)
        plugin.acknowledged_positions[plugin.target_id] = encode_cursor({
            'timestamp': 0,
            'fingerprints': [],
        })

        batches = plugin.collect_once(
            timestamp=datetime.fromtimestamp(2, timezone.utc)
        )

        self.assertEqual([len(batch['events']) for batch in batches], [3])
        self.assertEqual(
            len(decode_cursor(batches[0]['cursor'])['fingerprints']),
            3,
        )

    def test_boundary_cursor_retains_prior_fingerprints_at_same_millisecond(self):
        timestamp = 1000
        client = FakeKeycloakClient({
            0: [
                {'id': 'event-a', 'time': timestamp, 'type': 'LOGIN'},
                {'id': 'event-b', 'time': timestamp, 'type': 'LOGOUT'},
            ],
        })
        plugin = self.make_plugin(client)
        plugin.acknowledged_positions[plugin.target_id] = encode_cursor({
            'timestamp': timestamp,
            'fingerprints': ['event-a'],
        })

        batches = plugin.collect_once(
            timestamp=datetime.fromtimestamp(2, timezone.utc)
        )

        self.assertEqual(
            [event['data']['id'] for event in batches[0]['events']],
            ['event-b'],
        )
        self.assertEqual(
            decode_cursor(batches[0]['cursor']),
            {'timestamp': timestamp, 'fingerprints': ['event-a', 'event-b']},
        )

    def test_failed_target_is_not_polled_again(self):
        client = FakeKeycloakClient({
            0: [{'id': 'event-1', 'time': 1000, 'type': 'LOGIN'}],
        })
        plugin = self.make_plugin(client)
        plugin.failed_targets[plugin.target_id] = 'batch_id_reused'

        self.assertEqual(plugin.collect_once(), [])
        self.assertEqual(client.calls, [])


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class Session:
    def __init__(self):
        self.headers = {}
        self.posts = 0
        self.gets = 0

    def post(self, *_args, **_kwargs):
        self.posts += 1
        return Response(200, {'access_token': f'token-{self.posts}'})

    def get(self, *_args, **_kwargs):
        self.gets += 1
        if self.gets == 1:
            return Response(401, {'error': 'expired'})
        return Response(200, [{'id': 'event-1', 'time': 1}])


class KeycloakApiClientTests(SimpleTestCase):
    def test_401_refreshes_the_admin_token_once(self):
        session = Session()
        client = KeycloakApiClient(
            {
                'base_url': 'https://keycloak.example.test',
                'client_id': 'siematic-shipper',
                'client_secret': 'secret',
            },
            session=session,
        )

        events = client.fetch_events(
            'rossoctl', date_from=1, date_to=2, first=0, max_results=100
        )

        self.assertEqual(events[0]['id'], 'event-1')
        self.assertEqual(session.posts, 2)
        self.assertEqual(session.headers['Authorization'], 'Bearer token-2')
