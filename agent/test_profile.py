import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from agent.plugins.plugin_process_manager import config_log_summary
from agent.profile import load_profile


class ProfileLoaderTests(TestCase):
    def write_profile(self, profile):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'profile.json'
        path.write_text(json.dumps(profile), encoding='utf-8')
        return path

    def kube_profile(self):
        return {
            'version': 1,
            'plugin': 'kube_logs',
            'poll_interval': 5,
            'targets': [{
                'namespace': 'example-namespace',
                'deployment': 'example-deployment',
                'container': 'example-container',
                'index': 'example-index',
                'source': 'example-deployment/example-container',
                'sourcetype': 'logfmt',
            }],
        }

    def credentials(self):
        return {
            'INDEXER_USERNAME': 'example-indexer',
            'INDEXER_PASSWORD': 'example-indexer-secret',
        }

    def test_missing_file(self):
        with self.assertRaisesRegex(ValueError, 'profile file'):
            load_profile('missing-profile.json', self.credentials())

    def test_malformed_json(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'profile.json'
        path.write_text('{', encoding='utf-8')

        with self.assertRaisesRegex(ValueError, 'profile JSON'):
            load_profile(path, self.credentials())

    def test_unknown_plugin(self):
        profile = self.kube_profile()
        profile['plugin'] = 'example_plugin'

        with self.assertRaisesRegex(ValueError, 'plugin'):
            load_profile(self.write_profile(profile), self.credentials())

    def test_more_than_one_plugin(self):
        profile = self.kube_profile()
        profile['plugins'] = ['kube_logs', 'keycloak_events']

        with self.assertRaisesRegex(ValueError, 'plugin'):
            load_profile(self.write_profile(profile), self.credentials())

    def test_missing_required_field(self):
        profile = self.kube_profile()
        del profile['targets'][0]['source']

        with self.assertRaisesRegex(ValueError, 'source'):
            load_profile(self.write_profile(profile), self.credentials())

    def test_duplicate_target_id(self):
        profile = self.kube_profile()
        profile['targets'].append(dict(profile['targets'][0]))

        with self.assertRaisesRegex(ValueError, 'target id'):
            load_profile(self.write_profile(profile), self.credentials())

    def test_missing_credential(self):
        environ = self.credentials()
        del environ['INDEXER_PASSWORD']

        with self.assertRaisesRegex(ValueError, 'INDEXER_PASSWORD'):
            load_profile(self.write_profile(self.kube_profile()), environ)

    def test_keycloak_token_realm_is_required(self):
        profile = {
            'version': 1,
            'plugin': 'keycloak_events',
            'poll_interval': 30,
            'realm': 'example-realm',
            'index': 'example-index',
            'source': 'keycloak/example-realm',
            'host': 'example-keycloak',
        }
        environ = {
            **self.credentials(),
            'KEYCLOAK_BASE_URL': 'https://keycloak.example.test',
            'KEYCLOAK_CLIENT_ID': 'example-client',
            'KEYCLOAK_CLIENT_SECRET': 'example-secret',
        }

        with self.assertRaisesRegex(ValueError, 'KEYCLOAK_TOKEN_REALM'):
            load_profile(self.write_profile(profile), environ)

    def test_secret_values_are_not_in_startup_summary(self):
        plugin = load_profile(
            self.write_profile(self.kube_profile()),
            self.credentials(),
        )[0]

        summary = config_log_summary(plugin)
        self.assertNotIn('example-indexer-secret', summary)
        self.assertIn('indexer_credentials', summary)