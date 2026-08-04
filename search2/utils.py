import inspect
import logging
import time
from itertools import chain
from types import GeneratorType
from django.conf import settings
from django.db.models.query import QuerySet, ValuesIterable
import statistics
from collections import Counter
from datetime import datetime, date
import re

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_DATE_FORMATS = (
    '%Y-%m-%d',
    '%Y-%m-%d %H:%M:%S',
    '%m/%d/%Y',
    '%d/%m/%Y',
)


def _get_summary_date_formats():
    """Return the configured, validated formats used for date inference."""
    configured_formats = getattr(settings, 'SIEMATIC_SEARCH', {}).get(
        'SUMMARY_DATE_FORMATS', DEFAULT_SUMMARY_DATE_FORMATS
    )
    if not isinstance(configured_formats, (list, tuple)):
        logger.warning(
            'SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"] must be a list or tuple; '
            'using the default formats.'
        )
        return DEFAULT_SUMMARY_DATE_FORMATS

    valid_formats = tuple(
        date_format
        for date_format in configured_formats
        if isinstance(date_format, str) and date_format
    )
    if not valid_formats:
        logger.warning(
            'SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"] contains no valid formats; '
            'using the default formats.'
        )
        return DEFAULT_SUMMARY_DATE_FORMATS
    return valid_formats


def _short_repr(obj, length=200):
    try:
        r = repr(obj)
    except Exception:
        return f"<{type(obj).__name__} (unreprable)>"
    if len(r) > length:
        return r[:length] + '...'
    return r
# Cache model field access patterns to avoid repeated meta introspection
_MODEL_FIELD_CACHE: dict = {}


def _get_model_fields_info(model):
    """
    Return cached (field_keys, field_attnames, m2m_fields) for a model class.
    """
    try:
        return _MODEL_FIELD_CACHE[model]
    except KeyError:
        opts = model._meta
        regular_fields = list(chain(opts.concrete_fields, opts.private_fields))
        field_keys = [f.name for f in regular_fields]
        field_attnames = [getattr(f, 'attname', f.name) for f in regular_fields]
        m2m_fields = list(opts.many_to_many)
        info = (field_keys, field_attnames, m2m_fields)
        _MODEL_FIELD_CACHE[model] = info
        return info

def custom_model_to_dict(instance):
    """
    Convert a Django model instance to a dictionary.
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()
    logger.debug("custom_model_to_dict called with instance type: %s", type(instance).__name__)
    if isinstance(instance, dict):
        logger.info("Instance is already a dict, returning as-is")
        logger.debug("custom_model_to_dict completed in %.3fs", time.time() - start_time)
        return instance

    model = instance.__class__
    field_keys, field_attnames, m2m_fields = _get_model_fields_info(model)
    data = {}

    # Fast path for non-m2m fields: use attname to retrieve raw DB values (avoids calling value_from_object)
    for key, att in zip(field_keys, field_attnames):
        try:
            data[key] = getattr(instance, att)
        except Exception:
            # Fallback to attribute name
            data[key] = getattr(instance, key, None)

    # Handle many-to-many fields separately (may be prefetched)
    for f in m2m_fields:
        try:
            rel = getattr(instance, f.name)
            if hasattr(rel, 'values_list'):
                try:
                    data[f.name] = list(rel.values_list('pk', flat=True))
                except Exception:
                    data[f.name] = list(rel.all())
            else:
                data[f.name] = rel
        except Exception:
            data[f.name] = None
    logger.debug("Converted model instance to dict with %d fields", len(data))
    logger.debug("custom_model_to_dict completed in %.3fs", time.time() - start_time)
    return data

def coerce_to_list_of_dicts(results, serializer_cls=None):
    """
    Robustly convert results to a list of dicts for template rendering or JSON serialization.
    Handles QuerySet, list of model instances, list of dicts, dict, generator, and None.
    Optionally uses a serializer class for model instances.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    logger.info("Starting coerce_to_list_of_dicts with results type: %s, serializer_cls: %s",
                type(results).__name__ if results is not None else 'None',
                serializer_cls.__name__ if serializer_cls else 'None')
    
    if results is None:
        logger.warning("Received None as results, returning empty list")
        logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
        return []
    
    try:
        import pandas as pd
        if isinstance(results, pd.DataFrame):
            logger.debug("Converting pandas DataFrame to list of dicts")
            # Replace NaT values with None to avoid template rendering issues
            df = results.replace({pd.NaT: None})
            result_list = df.to_dict('records')
            logger.debug("Converted DataFrame with shape %s to %d records", results.shape, len(result_list))
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return result_list
    except ImportError:
        logger.warning("pandas not available, skipping DataFrame conversion")
        pass
    
    if inspect.isgeneratorfunction(results):
        logger.debug("Executing generator function to obtain results")
        try:
            results = results()
            logger.debug("Generator function executed successfully")
        except TypeError:
            logger.exception("Generator function requires arguments and cannot be executed")
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return []
    
    if isinstance(results, GeneratorType):
        logger.debug("Converting generator results to list")
        results = list(results)
        logger.debug("Converted generator to list with %d items", len(results))
    
    if isinstance(results, QuerySet):
        logger.debug("Converting QuerySet results to list of dicts (optimized)")
        # If serializer provided, try it first
        if serializer_cls and getattr(results, 'model', None):
            logger.debug("Using serializer class %s for QuerySet model %s", serializer_cls, results.model)
            try:
                result_list = serializer_cls(results, many=True).data
                logger.debug("Serializer converted %d QuerySet items", len(result_list))
                logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
                return result_list
            except Exception:
                logger.exception("Serializer failed, falling back to optimized values() conversion")

        # Try fast path: if already values queryset, just list it; else use values()
        #
        # `query.values_select` only tracks concrete-column selections. A
        # `.values()` call that groups by an annotated/computed field (e.g. a
        # TruncMinute() bucket) or by an aggregate puts those names in
        # `annotation_select` instead, leaving `values_select` empty even
        # though the queryset already yields dicts. Checking `_iterable_class`
        # is how Django itself distinguishes a `.values()` queryset, so it
        # covers both cases; the wrong check previously caused a second,
        # unrestricted `.values()` call that re-expanded grouped/aggregated
        # results back to full model rows.
        try:
            if results._iterable_class is ValuesIterable:
                vals = list(results)
            else:
                vals = list(results.values())
            # Normalize None fields across dicts
            if vals:
                keys = set(chain.from_iterable(d.keys() for d in vals))
                for d in vals:
                    for k in keys:
                        d.setdefault(k, None)
            logger.debug("Converted QuerySet to %d dict items", len(vals))
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return vals
        except Exception:
            logger.exception("Fast conversion failed; falling back to per-instance conversion")

        # Fallback: convert per instance using optimized custom_model_to_dict
        result_list = [custom_model_to_dict(item) for item in results]
        logger.debug("Converted QuerySet to %d dict items via per-instance conversion", len(result_list))
        logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
        return result_list
    
    if isinstance(results, list):
        if not results:
            logger.info("Empty list provided to coerce_to_list_of_dicts")
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return []
        
        if serializer_cls and all(hasattr(item, '_meta') for item in results):
            try:
                result_list = serializer_cls(results, many=True).data
                logger.debug("Serializer converted list of %d model instances", len(result_list))
                logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
                return result_list
            except Exception:
                logger.exception("Serializer failed for list, falling back to custom_model_to_dict")
                result_list = [custom_model_to_dict(item) for item in results]
                logger.debug("Fallback conversion completed for %d items", len(result_list))
                logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
                return result_list
        
        if all(isinstance(item, dict) for item in results):
            keys = set(chain.from_iterable(item.keys() for item in results))
            logger.debug("Normalizing %d dict items with %d total keys", len(results), len(keys))
            for item in results:
                for key in keys:
                    if key not in item:
                        item[key] = None
            logger.debug("All items are dicts, returning normalized list")
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return results
        
        if all(hasattr(item, '_meta') for item in results):
            logger.debug("All items are model instances, converting to dicts (optimized)")
            # Attempt fast per-model conversion using cached field info when all items share same model
            model = results[0].__class__
            if all(item.__class__ is model for item in results):
                field_keys, field_attnames, m2m_fields = _get_model_fields_info(model)
                out_list = []
                for inst in results:
                    row = {}
                    for key, att in zip(field_keys, field_attnames):
                        row[key] = getattr(inst, att, None)
                    for f in m2m_fields:
                        try:
                            rel = getattr(inst, f.name)
                            if hasattr(rel, 'values_list'):
                                row[f.name] = list(rel.values_list('pk', flat=True))
                            else:
                                row[f.name] = list(rel.all())
                        except Exception:
                            row[f.name] = None
                    out_list.append(row)
                logger.debug("Converted %d model instances to dicts (same model)", len(out_list))
                logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
                return out_list
            # Mixed models: fallback to custom_model_to_dict for safety
            result_list = [custom_model_to_dict(item) for item in results]
            logger.debug("Converted %d mixed-model instances to dicts", len(result_list))
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return result_list
        
        if all(isinstance(item, (list, tuple)) for item in results):
            logger.debug("All items are lists/tuples, converting to dicts")
            result_list = [dict(item) if hasattr(item, '__iter__') else {'value': item} for item in results]
            logger.debug("Converted %d list/tuple items", len(result_list))
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return result_list
        
        logger.debug("Returning list of values wrapped in dicts")
        result_list = [{'value': item} for item in results]
        logger.debug("Wrapped %d values in dicts", len(result_list))
        logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
        return result_list
    
    if serializer_cls and hasattr(results, '_meta'):
        try:
            result_list = [serializer_cls(results).data]
            logger.debug("Serializer converted single instance")
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return result_list
        except Exception:
            logger.exception("Serializer failed for single instance, falling back to custom_model_to_dict")
            result_list = [custom_model_to_dict(results)]
            logger.debug("Fallback conversion completed for single item")
            logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
            return result_list
    
    if hasattr(results, '_meta'):
        logger.debug("Single model instance, converting to dict")
        result_list = [custom_model_to_dict(results)]
        logger.debug("Converted single model instance")
        logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
        return result_list
    
    if isinstance(results, dict):
        logger.debug("Single dict provided, wrapping in list")
        logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
        return [results]
    
    logger.warning("Unknown results type %s, wrapping in dict", type(results).__name__)
    logger.debug("coerce_to_list_of_dicts completed in %.3fs", time.time() - start_time)
    return [{'value': results}]

def analyze_column_type(values):
    """
    Analyze a list of values to determine the column type and characteristics.
    Returns a dict with type info and statistics.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    logger.debug("Starting analyze_column_type for %d values", len(values))
    
    non_null_values = []
    for v in values:
        if v is not None and v != '':
            if hasattr(v, '__dict__') and hasattr(v, '_errors'):
                logger.warning("Skipping complex Django object: %s", type(v).__name__)
                continue
            if isinstance(v, (str, int, float, bool, datetime, date)):
                non_null_values.append(v)
    
    logger.debug("Found %d non-null values out of %d total", len(non_null_values), len(values))
    
    if not non_null_values:
        logger.info("All values are null or empty, returning empty type")
        logger.debug("analyze_column_type completed in %.3fs", time.time() - start_time)
        return {
            'type': 'empty',
            'null_count': len(values),
            'non_null_count': 0,
            'unique_count': 0
        }
    
    null_count = len(values) - len(non_null_values)
    try:
        unique_values = list(set(non_null_values))
        unique_count = len(unique_values)
    except TypeError:
        logger.warning("Values not hashable, counting unique values manually")
        unique_values = []
        for v in non_null_values:
            if v not in unique_values:
                unique_values.append(v)
        unique_count = len(unique_values)
    
    logger.debug("Column has %d unique values", unique_count)
    
    result = {
        'null_count': null_count,
        'non_null_count': len(non_null_values),
        'unique_count': unique_count,
    }
    
    # Try to determine type and calculate statistics
    numeric_values = []
    date_values = []
    summary_date_formats = _get_summary_date_formats()
    for v in non_null_values:
        try:
            if isinstance(v, (int, float)):
                numeric_values.append(float(v))
            elif isinstance(v, str) and re.match(r'^-?\d*\.?\d+$', v.strip()):
                numeric_values.append(float(v))
        except (ValueError, TypeError):
            logger.debug("Value %s could not be converted to float", repr(v))
            pass
    
    for v in non_null_values:
        try:
            if isinstance(v, (datetime, date)):
                date_values.append(v)
            elif isinstance(v, str):
                for fmt in summary_date_formats:
                    try:
                        parsed_date = datetime.strptime(v, fmt)
                        date_values.append(parsed_date)
                        break
                    except ValueError:
                        continue
        except (ValueError, TypeError):
            logger.debug("Value %s could not be converted to date", repr(v))
            pass
    
    # Filter out NaT values for date calculations (pandas may not be available)
    try:
        import pandas as pd
    except Exception:
        pd = None
    original_date_count = len(date_values)
    if pd is not None:
        date_values = [d for d in date_values if not (hasattr(d, 'isnull') and d.isnull()) and not pd.isna(d)]
    else:
        date_values = [d for d in date_values if not (hasattr(d, 'isnull') and d.isnull())]
    if len(date_values) < original_date_count:
        logger.debug("Filtered out %d NaT values from date analysis", original_date_count - len(date_values))
    
    logger.debug("Identified %d numeric values, %d date values", len(numeric_values), len(date_values))
    
    if len(date_values) == len(non_null_values):
        logger.debug("Classifying column as datetime")
        result['type'] = 'datetime'
        if date_values:
            result['min_date'] = min(date_values)
            result['max_date'] = max(date_values)
    elif len(numeric_values) == len(non_null_values):
        logger.debug("Classifying column as numeric")
        result['type'] = 'numeric'
        if numeric_values:
            result['min'] = min(numeric_values)
            result['max'] = max(numeric_values)
            result['mean'] = statistics.mean(numeric_values)
            result['median'] = statistics.median(numeric_values)
            try:
                result['mode'] = statistics.mode(numeric_values)
            except statistics.StatisticsError:
                result['mode'] = None
            try:
                # Calculate std dev manually using float arithmetic to avoid
                # issues with types that the statistics module may try to
                # coerce into Fraction-like objects (which can raise
                # "'float' object has no attribute 'numerator'"). We already
                # cast values to float above, so a manual calculation is
                # straightforward and robust.
                if len(numeric_values) > 1:
                    import math
                    mean_val = statistics.mean(numeric_values)
                    # sample variance (n-1 denominator)
                    var = sum((x - mean_val) ** 2 for x in numeric_values) / (len(numeric_values) - 1)
                    result['std_dev'] = math.sqrt(var)
                else:
                    result['std_dev'] = 0.0
            except Exception as e:
                logger.warning("Could not calculate std_dev: %s", e)
                result['std_dev'] = 0.0
    else:
        logger.debug("Classifying column as text")
        result['type'] = 'text'
        value_counts = Counter(non_null_values)
        result['most_common'] = value_counts.most_common(3)
        result['avg_length'] = sum(len(str(v)) for v in non_null_values) / len(non_null_values)
    
    logger.debug("analyze_column_type result: type=%s, completed in %.3fs", result.get('type'), time.time() - start_time)
    return result

def calculate_results_summary(results):
    """
    Calculate summary statistics for search results.
    Returns a dict with overall statistics and per-column analysis.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    logger.info("Starting calculate_results_summary")
    
    if not results or not isinstance(results, list):
        logger.warning("Invalid results input: not a list or empty (type=%s, repr=%s)",
                       type(results).__name__ if results is not None else 'None',
                       _short_repr(results))
        logger.debug("calculate_results_summary completed in %.3fs", time.time() - start_time)
        return {
            'total_rows': 0,
            'total_columns': 0,
            'columns': {}
        }
    
    logger.debug("Processing %d result rows", len(results))

    # Single-pass collection of top-level and nested column values.
    column_values = {}  # top-level column -> list of values (aligned to rows)
    nested_columns = {}  # flattened nested column -> list of values (only collected when present)
    dict_columns = set()

    def _flatten_map(prefix, d, out_map):
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _flatten_map(full_key, v, out_map)
            else:
                out_map[full_key] = v

    # Iterate once through results building column value lists.
    for row_idx, row in enumerate(results):
        if isinstance(row, dict):
            row_keys = set(row.keys())

            # Ensure lists exist for new columns and pad with None for prior rows
            for key in row_keys:
                if key not in column_values:
                    column_values[key] = [None] * row_idx
                column_values[key].append(row.get(key))

                # Handle nested dict values: flatten and collect per-nested-key lists
                v = row.get(key)
                if isinstance(v, dict):
                    dict_columns.add(key)
                    nested_map = {}
                    _flatten_map(key, v, nested_map)
                    for nested_key, nested_val in nested_map.items():
                        if nested_key not in nested_columns:
                            nested_columns[nested_key] = []
                        nested_columns[nested_key].append(nested_val)

            # For columns not present in this row, append None to keep alignment
            for key in list(column_values.keys()):
                if key not in row_keys:
                    column_values[key].append(None)
        else:
            # Non-dict row: append None for all known columns
            for key in list(column_values.keys()):
                column_values[key].append(None)

    logger.debug("Found %d unique columns across all rows", len(column_values))

    column_stats = {}
    # Analyze top-level non-dict columns
    for col_name, values in column_values.items():
        if col_name in dict_columns:
            logger.debug("Column %s contains nested dicts, will analyze flattened keys", col_name)
            continue
        logger.debug("Analyzing column: %s", col_name)
        column_stats[col_name] = analyze_column_type(values)

    # Analyze nested columns (flattened keys were collected during single pass)
    logger.debug("Analyzing %d nested columns", len(nested_columns))
    for nested_col, values in nested_columns.items():
        logger.debug("Analyzing nested column: %s", nested_col)
        column_stats[nested_col] = analyze_column_type(values)

    # Only count non-dict columns and nested columns in total_columns
    total_columns = (len(column_values) - len(dict_columns)) + len(nested_columns)
    logger.info("Summary calculated: %d rows, %d columns (%d dict columns flattened to %d nested)",
                len(results), total_columns, len(dict_columns), len(nested_columns))
    
    logger.debug("calculate_results_summary completed in %.3fs", time.time() - start_time)
    return {
        'total_rows': len(results),
        'total_columns': total_columns,
        'columns': column_stats
    }


def extract_field_names(results):
    """
    Extract all available field names from the results data.
    Returns a sorted list of field names suitable for chart dropdowns.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    logger.info("Starting extract_field_names")
    
    if not results or len(results) == 0:
        logger.warning("No results provided to extract_field_names (type=%s, repr=%s)",
                       type(results).__name__ if results is not None else 'None',
                       _short_repr(results))
        logger.debug("extract_field_names completed in %.3fs", time.time() - start_time)
        return []
    
    sample = results[0]
    if not isinstance(sample, dict):
        logger.warning("First result is not a dict, cannot extract field names")
        logger.debug("extract_field_names completed in %.3fs", time.time() - start_time)
        return []
    
    def flatten_keys(obj, prefix="", out=None, depth=0, max_depth=5):
        if out is None:
            out = []
        if depth > max_depth or obj is None:
            return out
        if isinstance(obj, list):
            return out
        if not isinstance(obj, dict):
            return out
        for key, value in obj.items():
            field_path = f"{prefix}__{key}" if prefix else key
            if (value is None or 
                isinstance(value, (str, int, float, bool)) or
                hasattr(value, 'isoformat')):
                out.append(field_path)
            elif isinstance(value, dict) and not isinstance(value, list):
                flatten_keys(value, field_path, out, depth + 1, max_depth)
        return out
    
    field_names = flatten_keys(sample)
    logger.debug("Extracted %d field names from first sample", len(field_names))
    
    if len(results) > 1:
        additional_count = 0
        for i in range(1, min(5, len(results))):
            if isinstance(results[i], dict):
                additional_fields = flatten_keys(results[i])
                field_names.extend(additional_fields)
                additional_count += len(additional_fields)
        logger.debug("Added %d additional field names from %d more samples", additional_count, min(5, len(results)) - 1)
    
    unique_field_names = sorted(set(field_names))
    logger.info("Extracted %d unique field names total", len(unique_field_names))
    logger.debug("extract_field_names completed in %.3fs", time.time() - start_time)
    return unique_field_names


def debug_results_structure(results):
    """
    Debug utility to see the structure of results data.
    Use this to understand why fields might be missing.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    logger.info("Starting debug_results_structure")
    
    if not results:
        logger.warning("No results provided to debug_results_structure")
        logger.debug("debug_results_structure completed in %.3fs", time.time() - start_time)
        return "No results provided"
    
    if len(results) == 0:
        logger.warning("Empty results list in debug_results_structure")
        logger.debug("debug_results_structure completed in %.3fs", time.time() - start_time)
        return "Empty results list"
    
    sample = results[0]
    logger.debug("Analyzing structure of first result (type: %s)", type(sample).__name__)
    
    def analyze_structure(obj, prefix="", depth=0, max_depth=3):
        if depth > max_depth:
            return f"{prefix}: [max depth reached]"
        if obj is None:
            return f"{prefix}: None"
        elif isinstance(obj, (str, int, float, bool)):
            return f"{prefix}: {type(obj).__name__} = {repr(obj)}"
        elif isinstance(obj, list):
            if len(obj) == 0:
                return f"{prefix}: empty list"
            else:
                return f"{prefix}: list[{len(obj)}] (first: {type(obj[0]).__name__})"
        elif isinstance(obj, dict):
            result = [f"{prefix}: dict with keys: {list(obj.keys())}"]
            for key, value in obj.items():
                field_path = f"{prefix}.{key}" if prefix else key
                result.append(analyze_structure(value, field_path, depth + 1, max_depth))
            return "\n".join(result)
        else:
            return f"{prefix}: {type(obj).__name__}"
    
    structure = analyze_structure(sample)
    logger.debug("Results structure analysis completed")
    logger.debug("debug_results_structure completed in %.3fs", time.time() - start_time)
    return structure


def debug_timestamp_fields(results, field1="created", field2="created_second"):
    """Return a readable comparison of two timestamp fields."""
    if not results:
        return "No results to debug"

    output = [f"Debugging {field1} vs {field2}", "=" * 50]
    for index, result in enumerate(results[:10]):
        if not isinstance(result, dict):
            continue
        value1 = result.get(field1, "MISSING")
        value2 = result.get(field2, "MISSING")
        output.extend([
            f"Row {index + 1}:",
            f"  {field1}: {value1} (type: {type(value1).__name__})",
            f"  {field2}: {value2} (type: {type(value2).__name__})",
        ])
        if isinstance(value1, str) and isinstance(value2, str):
            if value1 == value2:
                output.append("  \N{RIGHTWARDS ARROW} VALUES ARE IDENTICAL")
            else:
                output.append(
                    f"  \N{RIGHTWARDS ARROW} Difference: "
                    f"{len(value1) - len(value2)} chars"
                )
        output.append("")
    return "\n".join(output)
