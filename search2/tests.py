from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.test import APIClient

from search2.api import Search2RunView
from search2.commands.run_saved_search import RunSavedSearchCommand
from search2.engine.core import PipelineArgumentError, run_pipeline
from .models import SavedSearch
from .utils import (
    analyze_column_type,
    coerce_to_list_of_dicts,
    debug_results_structure,
    debug_timestamp_fields,
    extract_field_names,
)

User = get_user_model()

class SavedSearchCRUDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_create_savedsearch(self):
        url = reverse('savedsearch_create')
        data = {'name': 'Test Search', 'query': 'foo:bar'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SavedSearch.objects.filter(name='Test Search', owner=self.user).exists())

    def test_list_savedsearches(self):
        SavedSearch.objects.create(owner=self.user, name='ListTest', query='a:b')
        url = reverse('savedsearch_list')
        response = self.client.get(url)
        self.assertContains(response, 'ListTest')

    def test_update_savedsearch(self):
        ss = SavedSearch.objects.create(owner=self.user, name='Old', query='x:y')
        url = reverse('savedsearch_update', args=[ss.pk])
        response = self.client.post(url, {'name': 'New', 'query': 'z:w'})
        self.assertEqual(response.status_code, 302)
        ss.refresh_from_db()
        self.assertEqual(ss.name, 'New')

    def test_delete_savedsearch(self):
        ss = SavedSearch.objects.create(owner=self.user, name='Del', query='q:r')
        url = reverse('savedsearch_delete', args=[ss.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SavedSearch.objects.filter(pk=ss.pk).exists())

    @patch('search2.engine.core.run_pipeline', return_value=[{'host': 'preview-host'}])
    def test_create_preview_embeds_rows_for_datatable(self, run_pipeline):
        response = self.client.post(
            reverse('savedsearch_create'),
            {'name': 'Preview', 'query': 'search', 'preview': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-results-json"')
        self.assertContains(response, 'preview-host')
        run_pipeline.assert_called_once()

    @patch('search2.engine.core.run_pipeline', return_value=[{'host': 'edited-preview-host'}])
    def test_update_preview_embeds_rows_for_datatable(self, run_pipeline):
        saved_search = SavedSearch.objects.create(
            owner=self.user,
            name='Preview',
            query='search',
        )

        response = self.client.post(
            reverse('savedsearch_update', args=[saved_search.pk]),
            {'name': 'Preview', 'query': 'search', 'preview': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-results-json"')
        self.assertContains(response, 'edited-preview-host')
        run_pipeline.assert_called_once()


class SavedSearchVisibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='testpass')
        self.viewer = User.objects.create_user(username='viewer', password='testpass')
        self.third_party = User.objects.create_user(username='third', password='testpass')
        self.client = Client()
        self.client.login(username='viewer', password='testpass')
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.viewer)

        self.viewer_own = SavedSearch.objects.create(owner=self.viewer, name='Viewer Own', query='search viewer')
        self.shared = SavedSearch.objects.create(owner=self.owner, name='Shared Search', query='search shared')
        self.shared.shared_with.add(self.viewer)
        self.public = SavedSearch.objects.create(owner=self.owner, name='Public Search', query='search public', is_public=True)
        self.private_other = SavedSearch.objects.create(owner=self.owner, name='Private Other', query='search private')

    def test_savedsearch_list_shows_visible_searches_only(self):
        response = self.client.get(reverse('savedsearch_list'))

        self.assertContains(response, 'Viewer Own')
        self.assertContains(response, 'Shared Search')
        self.assertContains(response, 'Public Search')
        self.assertNotContains(response, 'Private Other')

    def test_savedsearch_api_lists_visible_searches_only(self):
        response = self.api_client.get(reverse('savedsearch-list'))

        self.assertEqual(response.status_code, 200)
        names = {item['name'] for item in response.json()}
        self.assertSetEqual(names, {'Viewer Own', 'Shared Search', 'Public Search'})

    def test_savedsearch_api_update_stays_owner_only(self):
        response = self.api_client.patch(
            reverse('savedsearch-detail', args=[self.shared.pk]),
            {'query': 'changed'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)

    def test_run_saved_search_prefers_owned_search_on_duplicate_name(self):
        SavedSearch.objects.create(owner=self.viewer, name='Duplicate', query='search mine')
        other = SavedSearch.objects.create(owner=self.owner, name='Duplicate', query='search theirs')
        other.shared_with.add(self.viewer)

        command = RunSavedSearchCommand()
        ctx = SimpleNamespace(request=SimpleNamespace(user=self.viewer))
        args = SimpleNamespace(name='Duplicate', events=None)

        with patch('search2.commands.run_saved_search.run_pipeline', return_value=[]) as run_pipeline:
            command._run(None, args, ctx)

        run_pipeline.assert_called_once_with(None, 'search mine', request=ctx.request)

    def test_run_saved_search_rejects_unshared_search(self):
        command = RunSavedSearchCommand()
        ctx = SimpleNamespace(request=SimpleNamespace(user=self.viewer))
        args = SimpleNamespace(name='Private Other', events=None)

        with self.assertRaisesMessage(ValueError, "does not exist or is not shared with you"):
            command._run(None, args, ctx)

    def test_run_saved_search_rejects_ambiguous_shared_name(self):
        first = SavedSearch.objects.create(owner=self.owner, name='Ambiguous', query='search one', is_public=True)
        second = SavedSearch.objects.create(owner=self.third_party, name='Ambiguous', query='search two')
        second.shared_with.add(self.viewer)

        command = RunSavedSearchCommand()
        ctx = SimpleNamespace(request=SimpleNamespace(user=self.viewer))
        args = SimpleNamespace(name='Ambiguous', events=None)

        with self.assertRaisesMessage(ValueError, "Multiple shared or public SavedSearch objects named 'Ambiguous'"):
            command._run(None, args, ctx)

        first.delete()


class SearchApiThrottleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='throttleuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_search_api_throttles_after_limit(self):
        cache.clear()
        class TestSearchThrottle(ScopedRateThrottle):
            THROTTLE_RATES = {'search': '2/min'}

        original_throttle_classes = Search2RunView.throttle_classes
        Search2RunView.throttle_classes = [TestSearchThrottle]
        try:
            with patch('search2.api.run_pipeline', return_value=[]):
                first = self.client.post(reverse('search2_run_api'), {'query': 'search index=default'}, format='json')
                second = self.client.post(reverse('search2_run_api'), {'query': 'search index=default'}, format='json')
                third = self.client.post(reverse('search2_run_api'), {'query': 'search index=default'}, format='json')
        finally:
            Search2RunView.throttle_classes = original_throttle_classes

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)

class PipelineArgumentErrorTests(TestCase):
    """A malformed pipeline stage must not be able to take the whole server down.

    argparse's default error handling calls ``sys.exit()``, raising ``SystemExit``.
    Since ``SystemExit`` is a ``BaseException`` and not an ``Exception``, it slips
    past an ``except Exception`` in a view and crashes the request-handling process.
    """

    def test_missing_required_argument_raises_pipeline_error_not_systemexit(self):
        user = User.objects.create_user(username='groupbyerroruser', password='testpass')
        request = SimpleNamespace(user=user)
        with self.assertRaises(PipelineArgumentError):
            run_pipeline(None, "search --limit=1 | groupby", request=request)

    def test_unrecognized_argument_raises_pipeline_error_not_systemexit(self):
        with self.assertRaises(PipelineArgumentError):
            run_pipeline(None, "search --not-a-real-flag=1")

    def test_api_returns_400_instead_of_crashing(self):
        user = User.objects.create_user(username='pipelineerroruser', password='testpass')
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            reverse('search2_run_api'), {'query': 'search --limit=1 | groupby'}, format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())


class CoerceGroupedByAnnotationTests(TestCase):
    """coerce_to_list_of_dicts must not re-expand a values() queryset grouped by
    an annotated/computed field (e.g. a TruncMinute() bucket) back into full
    model rows.

    ``query.values_select`` only tracks concrete-column selections; grouping by
    an annotation instead populates ``query.annotation_select``, leaving
    ``values_select`` empty even though the queryset already yields dicts. A
    truthiness check on ``values_select`` alone treated that case as "not yet a
    values() queryset" and called ``.values()`` again with no field list, which
    resets the restriction and returns every model field plus the annotations.
    """

    def setUp(self):
        from events.models import Event

        self.user = User.objects.create_user(username='groupbyannotationuser', password='testpass')
        self.request = SimpleNamespace(user=self.user)
        Event.objects.create(index='sysmon', data='{"cpu_percent": 10}', sourcetype='json')
        Event.objects.create(index='sysmon', data='{"cpu_percent": 20}', sourcetype='json')

    def test_groupby_on_annotated_field_returns_grouped_rows(self):
        result = run_pipeline(
            None,
            "search --filter='index=\"sysmon\"' | "
            "annotate --set='minute=TruncMinute(created)' | "
            "groupby --keys='[\"minute\"]'",
            request=self.request,
        )
        rows = coerce_to_list_of_dicts(result)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), {'minute', 'count'})
        self.assertEqual(rows[0]['count'], 2)


class FieldExtractionTests(TestCase):
    """Tests for the extract_field_names utility function."""
    
    def test_extract_field_names_simple_dict(self):
        """Test field extraction from simple flat dictionary."""
        results = [
            {"id": 1, "name": "test", "count": 42, "active": True}
        ]
        fields = extract_field_names(results)
        expected = ["active", "count", "id", "name"]
        self.assertEqual(fields, expected)
    
    def test_extract_field_names_nested_dict(self):
        """Test field extraction from nested dictionary."""
        results = [
            {
                "id": 1,
                "user": {"name": "john", "email": "john@example.com"},
                "metadata": {"created": "2024-01-01", "tags": ["a", "b"]}
            }
        ]
        fields = extract_field_names(results)
        expected = ["id", "metadata__created", "user__email", "user__name"]
        self.assertEqual(fields, expected)
    
    def test_extract_field_names_with_datetime_fields(self):
        """Test field extraction with datetime fields."""
        results = [
            {
                "cpu_percent": 85.2,
                "host": "server1",
                "created": "2024-10-02T10:30:00Z",
                "created_second": "2024-10-02T10:30:15Z"
            }
        ]
        fields = extract_field_names(results)
        expected = ["cpu_percent", "created", "created_second", "host"]
        self.assertEqual(fields, expected)
    
    def test_extract_field_names_empty_results(self):
        """Test field extraction from empty results."""
        self.assertEqual(extract_field_names([]), [])
        self.assertEqual(extract_field_names(None), [])
    
    def test_extract_field_names_non_dict_results(self):
        """Test field extraction from non-dictionary results."""
        results = ["string1", "string2"]
        fields = extract_field_names(results)
        self.assertEqual(fields, [])
    
    def test_extract_field_names_mixed_types(self):
        """Test field extraction with mixed data types."""
        results = [
            {
                "string_field": "text",
                "int_field": 123,
                "float_field": 45.67,
                "bool_field": True,
                "null_field": None,
                "nested": {"inner": "value"}
            }
        ]
        fields = extract_field_names(results)
        expected = ["bool_field", "float_field", "int_field", "nested__inner", "null_field", "string_field"]
        self.assertEqual(fields, expected)

    def test_extract_field_names_multiple_samples(self):
        """Test field extraction from multiple samples with different fields."""
        results = [
            {"cpu_percent": 85.2, "host": "server1"},  # Missing created fields
            {"cpu_percent": 90.1, "host": "server2", "created": "2024-10-02T10:30:00Z"},  # Has created
            {"cpu_percent": 75.5, "host": "server3", "created_second": "2024-10-02T10:30:15Z"}  # Has created_second
        ]
        fields = extract_field_names(results)
        expected = ["cpu_percent", "created", "created_second", "host"]
        self.assertEqual(fields, expected)

    def test_debug_results_structure(self):
        """Test the debug utility function."""
        results = [
            {
                "cpu_percent": 85.2,
                "host": "server1", 
                "created": "2024-10-02T10:30:00Z",
                "nested": {"inner": "value"}
            }
        ]
        debug_output = debug_results_structure(results)
        # The debug function should show us the structure
        self.assertIn("cpu_percent", debug_output)
        self.assertIn("host", debug_output)
        self.assertIn("created", debug_output)


class SummaryDateFormatTests(TestCase):
    def test_default_date_format_is_detected(self):
        summary = analyze_column_type(['2026-08-03', '2026-08-04'])

        self.assertEqual(summary['type'], 'datetime')

    def test_numeric_values_remain_numeric(self):
        summary = analyze_column_type(['2026.215', '2026.216'])

        self.assertEqual(summary['type'], 'numeric')

    def test_configured_custom_date_format_is_detected(self):
        search_settings = {
            **settings.SIEMATIC_SEARCH,
            'SUMMARY_DATE_FORMATS': ['%Y.%j'],
        }

        with override_settings(SIEMATIC_SEARCH=search_settings):
            summary = analyze_column_type(['2026.215', '2026.216'])

        self.assertEqual(summary['type'], 'datetime')
        self.assertEqual(summary['min_date'], datetime(2026, 8, 3))
        self.assertEqual(summary['max_date'], datetime(2026, 8, 4))

    def test_invalid_date_format_configuration_uses_defaults(self):
        search_settings = {
            **settings.SIEMATIC_SEARCH,
            'SUMMARY_DATE_FORMATS': 'not-a-list',
        }

        with override_settings(SIEMATIC_SEARCH=search_settings):
            summary = analyze_column_type(['2026-08-03', '2026-08-04'])

        self.assertEqual(summary['type'], 'datetime')


class TimestampDebugTests(TestCase):
    """Tests for timestamp debugging utilities."""
    
    def test_debug_timestamp_fields(self):
        """Test timestamp field debugging."""
        results = [
            {
                "created": "2024-10-02T10:30:00.000Z",
                "created_second": "2024-10-02T10:30:00.000Z",  # Identical
                "cpu_percent": 85.2
            },
            {
                "created": "2024-10-02T10:30:01.500Z",
                "created_second": "2024-10-02T10:30:01.000Z",  # Different precision
                "cpu_percent": 90.1
            }
        ]
        
        debug_output = debug_timestamp_fields(results, "created", "created_second")
        
        # Should identify identical values
        self.assertIn("VALUES ARE IDENTICAL", debug_output)
        # Should show the different precisions
        self.assertIn("2024-10-02T10:30:01.500Z", debug_output)
        self.assertIn("2024-10-02T10:30:01.000Z", debug_output)
    
    def test_debug_empty_results(self):
        """Test debug with empty results."""
        debug_output = debug_timestamp_fields([], "created", "created_second")
        self.assertEqual(debug_output, "No results to debug")


class TruncSecondTests(TestCase):
    """Tests for TruncSecond functionality."""
    
    def test_truncsecond_import(self):
        """Test that TruncSecond can be imported and is available."""
        from search2.engine.expression_util import SUPPORTED_FUNCTIONS
        
        # Check that TruncSecond is available in the function mapping
        self.assertIn('TruncSecond', SUPPORTED_FUNCTIONS)

        # Get the TruncSecond function
        trunc_second_config = SUPPORTED_FUNCTIONS['TruncSecond']
        self.assertIn('qs', trunc_second_config)
        
        # Import the actual Django function to verify it works
        from django.db.models.functions import TruncSecond
        self.assertTrue(callable(TruncSecond))


class ChartComponentTests(TestCase):
    """Tests for the ChartComponent functionality."""
    
    def test_chart_component_context_with_results(self):
        """Test that chart component includes field names in context."""
        from search2.components.chart import ChartComponent
        
        results = [
            {"timestamp": "2024-01-01", "value": 100, "host": "server1"},
            {"timestamp": "2024-01-02", "value": 200, "host": "server2"}
        ]
        
        component = ChartComponent()
        context = component.get_context_data(results=results)
        
        self.assertIn("available_fields", context)
        self.assertIn("results", context)
        
        # Check that fields are extracted correctly
        expected_fields = ["host", "timestamp", "value"]
        self.assertEqual(context["available_fields"], expected_fields)
    
    def test_chart_component_context_empty_results(self):
        """Test chart component context with empty results."""
        from search2.components.chart import ChartComponent
        
        component = ChartComponent()
        context = component.get_context_data(results=[])
        
        self.assertIn("available_fields", context)
        self.assertEqual(context["available_fields"], [])


class PipelineCommandTests(TestCase):
    def setUp(self):
        self.rows = [
            {"host": "beta", "value": 2, "tags": {"kind": "server"}},
            {"host": "alpha", "value": 1, "tags": {"kind": "client"}},
            {"host": "alpha", "value": 3, "tags": {"kind": "client"}},
        ]

    def test_record_pipeline_commands(self):
        cases = {
            "filter --condition='host=\"alpha\"'": 2,
            "sort --fields='[\"host\", \"value\"]'": 3,
            "head --n=1": 1,
            "tail --n=1": 1,
            "unique --fields='[\"host\"]'": 2,
            "rename --mapping='{\"host\": \"machine\"}'": 3,
            "groupby --keys='[\"host\"]' --out=total": 2,
            "stats --aggregations='[\"count\"]' --by='[\"host\"]'": 2,
            "annotate --set='answer=1+2'": 3,
        }
        for query, expected_length in cases.items():
            with self.subTest(command=query.split()[0]):
                result = run_pipeline(self.rows, query)
                self.assertEqual(len(result), expected_length)

    def test_explode_and_to_dataframe_commands(self):
        result = run_pipeline(
            self.rows,
            "explode --field=tags | to_dataframe",
        )
        self.assertNotIn("tags", result.columns)
        self.assertEqual(
            list(result["tags_kind"]),
            ["server", "client", "client"],
        )

    def test_explode_records_removes_source_field_and_preserves_backend(self):
        result = run_pipeline(self.rows, "explode --field=tags")

        self.assertIsInstance(result, list)
        self.assertNotIn("tags", result[0])
        self.assertEqual(result[0]["tags_kind"], "server")

    def test_event_split_expands_record_arrays_and_retains_other_fields(self):
        rows = [
            {"host": "alpha", "tags": ["one", "two"], "value": 7},
            {"host": "beta", "tags": "scalar", "value": 8},
            {"host": "gamma", "tags": [], "value": 9},
            {"host": "delta", "value": 10},
        ]

        result = run_pipeline(rows, "event_split --field=tags")

        self.assertEqual(
            result,
            [
                {"host": "alpha", "tags": "one", "value": 7},
                {"host": "alpha", "tags": "two", "value": 7},
                {"host": "beta", "tags": "scalar", "value": 8},
                {"host": "delta", "value": 10},
            ],
        )
        self.assertEqual(rows[0]["tags"], ["one", "two"])

    def test_event_split_preserves_dataframe_backend(self):
        import pandas as pd

        dataframe = pd.DataFrame([
            {"host": "alpha", "tags": ["one", "two"], "value": 7},
            {"host": "beta", "tags": "scalar", "value": 8},
            {"host": "gamma", "tags": [], "value": 9},
        ])

        result = run_pipeline(dataframe, "event_split --field=tags")

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(list(result["host"]), ["alpha", "alpha", "beta"])
        self.assertEqual(list(result["tags"]), ["one", "two", "scalar"])
        self.assertEqual(list(result["value"]), [7, 7, 8])

    def test_event_split_materializes_model_queryset_as_records(self):
        from events.models import Event

        Event.objects.create(
            host="queryset-host",
            extracted_fields=[{"code": 200}, {"code": 201}],
        )

        result = run_pipeline(
            Event.objects.filter(host="queryset-host"),
            "event_split --field=extracted_fields",
        )

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["host"], "queryset-host")
        self.assertEqual(result[0]["extracted_fields"], {"code": 200})
        self.assertEqual(result[1]["extracted_fields"], {"code": 201})

    def test_event_split_preserves_values_queryset_projection(self):
        from events.models import Event

        Event.objects.create(
            host="projected-host",
            extracted_fields=["one", "two"],
        )

        result = run_pipeline(
            Event.objects.filter(host="projected-host").values(
                "host", "extracted_fields"
            ),
            "event_split --field=extracted_fields",
        )

        self.assertEqual(
            result,
            [
                {"host": "projected-host", "extracted_fields": "one"},
                {"host": "projected-host", "extracted_fields": "two"},
            ],
        )

    def test_drop_supports_records_and_dataframes(self):
        import pandas as pd

        query = "drop --fields='[\"host\", \"tags\"]'"
        records = run_pipeline(self.rows, query)
        dataframe = run_pipeline(pd.DataFrame(self.rows), query)

        self.assertEqual(set(records[0]), {"value"})
        self.assertEqual(list(dataframe.columns), ["value"])

    def test_drop_ignores_fields_that_are_not_present(self):
        result = run_pipeline(self.rows, "drop --fields='[\"missing\"]'")

        self.assertEqual(result, self.rows)

    def test_drop_and_explode_support_querysets(self):
        from events.models import Event

        Event.objects.create(
            host="queryset-host",
            extracted_fields={"kind": "server", "code": 200},
        )

        dropped = run_pipeline(
            Event.objects.all(),
            "drop --fields='[\"data\", \"source\"]'",
        )
        dropped_row = list(dropped)[0]
        self.assertNotIn("data", dropped_row)
        self.assertNotIn("source", dropped_row)

        projected = run_pipeline(
            Event.objects.values("host", "data"),
            "drop --fields='[\"data\"]'",
        )
        self.assertEqual(list(projected), [{"host": "queryset-host"}])

        no_fields = run_pipeline(
            Event.objects.values("host"),
            "drop --fields='[\"host\"]'",
        )
        self.assertEqual(no_fields, [{}])

        exploded = run_pipeline(
            Event.objects.filter(host="queryset-host"),
            "explode --field=extracted_fields",
        )
        exploded_row = list(exploded)[0]
        self.assertNotIn("extracted_fields", exploded_row)
        self.assertEqual(exploded_row["extracted_fields_kind"], "server")
        self.assertEqual(exploded_row["extracted_fields_code"], 200)

    def test_pipeline_substitutes_environment_parameters(self):
        result = run_pipeline(
            self.rows,
            "head --n={row_limit:d}",
            environ={"row_limit": 2},
        )
        self.assertEqual(len(result), 2)

    @patch("search2.commands.join.JoinCmd._get_right_df")
    def test_join_command(self, get_right_df):
        import pandas as pd

        get_right_df.return_value = pd.DataFrame([
            {"host": "alpha", "owner": "soc"},
        ])
        result = run_pipeline(
            self.rows,
            "join --on='[\"host\"]' --how=inner",
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(set(result["owner"]), {"soc"})


class SearchAuthorizationAndLimitsTests(TestCase):
    def setUp(self):
        from events.models import Event

        self.user = User.objects.create_user(
            username="pipeline-user",
            password="testpass",
        )
        self.request = SimpleNamespace(user=self.user)
        for number in range(3):
            Event.objects.create(
                data=f'{{"number": {number}}}',
                sourcetype="json",
            )

    def test_sensitive_models_are_denied(self):
        for model in ("project.CustomUser", "search2.SavedSearch"):
            with self.subTest(model=model), self.assertRaises(PermissionDenied):
                run_pipeline(
                    None,
                    f"search --model={model}",
                    request=self.request,
                )

    def test_max_rows_truncates_queryset_results(self):
        search_settings = {**settings.SIEMATIC_SEARCH, "MAX_ROWS": 2}
        with override_settings(SIEMATIC_SEARCH=search_settings):
            result = run_pipeline(None, "search", request=self.request)
        self.assertEqual(len(result), 2)
