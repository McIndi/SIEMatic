from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.test import APIClient

from search2.api import Search2RunView
from search2.commands.run_saved_search import RunSavedSearchCommand
from .models import SavedSearch
from .utils import extract_field_names, debug_results_structure

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

def debug_timestamp_fields(results, field1="created", field2="created_second"):
    """
    Debug function to compare two timestamp fields and show their actual values.
    Use this to understand why charts might look identical.
    """
    if not results:
        return "No results to debug"
    
    output = []
    output.append(f"Debugging {field1} vs {field2}")
    output.append("=" * 50)
    
    # Check first 10 results
    for i, result in enumerate(results[:10]):
        if not isinstance(result, dict):
            continue
            
        val1 = result.get(field1, "MISSING")
        val2 = result.get(field2, "MISSING")
        
        output.append(f"Row {i+1}:")
        output.append(f"  {field1}: {val1} (type: {type(val1).__name__})")
        output.append(f"  {field2}: {val2} (type: {type(val2).__name__})")
        
        # If both are strings, compare them
        if isinstance(val1, str) and isinstance(val2, str):
            if val1 == val2:
                output.append("  → VALUES ARE IDENTICAL")
            else:
                output.append(f"  → Difference: {len(val1) - len(val2)} chars")
        output.append("")
    
    return "\n".join(output)


def debug_chart_data_processing(results, x_field, y_field, by_field=None):
    """
    Debug how chart data processing affects the values.
    """
    from search2.static.search2.chart import formatLabel, getByPath
    
    output = []
    output.append(f"Chart Data Processing Debug")
    output.append(f"X Field: {x_field}, Y Field: {y_field}, By Field: {by_field}")
    output.append("=" * 60)
    
    # Process first few results like the chart does
    for i, row in enumerate(results[:5]):
        xValue = getByPath(row, x_field) if hasattr(row, 'get') else row.get(x_field)
        yValue = getByPath(row, y_field) if hasattr(row, 'get') else row.get(y_field)
        
        if xValue is not None:
            formatted_x = formatLabel(xValue)
            output.append(f"Row {i+1}:")
            output.append(f"  Raw X: {xValue} (type: {type(xValue).__name__})")
            output.append(f"  Formatted X: {formatted_x}")
            output.append(f"  Y: {yValue}")
            output.append("")
    
    return "\n".join(output)

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
        print(f"Debug output:\n{debug_output}")
        
        # The debug function should show us the structure
        self.assertIn("cpu_percent", debug_output)
        self.assertIn("host", debug_output)
        self.assertIn("created", debug_output)


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
