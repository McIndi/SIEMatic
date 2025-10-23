import logging
from search2.engine.core import run_pipeline
import pandas as pd

logger = logging.getLogger(__name__)

class JoinCmd:
    """Join command for combining data from current pipeline with another dataset.
    Examples:
        join --model='events.Event' --on='["field1", "field2"]' --how='left' --using='other_db' --filter='host="server1"'
    """
    name = "join"

    def add_arguments(self, p):
        p.add_argument(
            "--model",
            default="events.Event",
            help="Django model to query for the join data, in app_label.ModelName format (default: events.Event)",
        )
        p.add_argument(
            "--filter",
            action="append",
            default=[],
            help="Django ORM filter expression for join data, e.g. 'field__lookup=value'",
        )
        p.add_argument(
            "--exclude",
            action="append",
            default=[],
            help="Django ORM exclude expression for join data, e.g. 'field__lookup=value'",
        )
        p.add_argument(
            "--select",
            default=None,
            help="Django ORM select expression for join data, e.g. '[\"field1\", \"field2\"]'",
        )
        p.add_argument(
            "--on",
            required=True,
            help="List of fields to join on, e.g. '[\"field1\", \"field2\"]'",
        )
        p.add_argument(
            "--how",
            default="left",
            choices=["left", "right", "inner", "outer"],
            help="Type of join (default: left)",
        )
        p.add_argument(
            "--using",
            default="default",
            help="Database alias for the joined data (default: default)",
        )
        p.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit the number of results returned",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("join command requires input data")

    def run_qs(self, qs, args, ctx):
        """Convert QuerySet to DataFrame and perform join."""
        from django_pandas.io import read_frame
        df_left = read_frame(qs)
        df_right = self._get_right_df(args, ctx)
        return self._perform_join(df_left, df_right, args)

    def run_df(self, df, args, ctx):
        """Perform join on DataFrame."""
        df_right = self._get_right_df(args, ctx)
        return self._perform_join(df, df_right, args)

    def run_records(self, rows, args, ctx):
        """Convert records to DataFrame and perform join."""
        df_left = pd.DataFrame(rows)
        df_right = self._get_right_df(args, ctx)
        return self._perform_join(df_left, df_right, args)

    def _get_right_df(self, args, ctx):
        """Get the right DataFrame by running a search query with the specified parameters."""
        query_parts = [f"search --using='{args.using}' --model='{args.model}'"]
        
        if getattr(args, 'limit', None) is not None:
            query_parts.append(f"--limit={args.limit}")

        for f in getattr(args, 'filter', []):
            query_parts.append(f"--filter='{f}'")
        
        for e in getattr(args, 'exclude', []):
            query_parts.append(f"--exclude='{e}'")
        
        if getattr(args, 'select', None):
            query_parts.append(f"--select='{args.select}'")
        
        query = " ".join(query_parts)
        logger.info(f"Running right-side query: {query}")
        
        result = run_pipeline(None, query, request=ctx.request)
        logger.info(f"Right-side query result type: {type(result)}")
        
        # Convert result to DataFrame
        if isinstance(result, pd.DataFrame):
            logger.info(f"Right DataFrame shape: {result.shape}")
            return result
        elif isinstance(result, list):
            df = pd.DataFrame(result)
            logger.info(f"Right DataFrame from list shape: {df.shape}")
            return df
        else:
            # Assume it's a QuerySet or similar iterable
            from django.db.models import QuerySet
            if isinstance(result, QuerySet):
                from django_pandas.io import read_frame
                df = read_frame(result)
                logger.info(f"Right DataFrame from QuerySet shape: {df.shape}")
                return df
            else:
                raise ValueError(f"Unsupported result type from search: {type(result)}")

    def _perform_join(self, df_left, df_right, args):
        """Perform the pandas merge."""
        from search2.engine.literals import parse_literal_list
        on_fields = parse_literal_list(args.on, "--on")
        logger.info(f"Performing {args.how} join on fields {on_fields}")
        logger.info(f"Left DataFrame shape: {df_left.shape}, columns: {list(df_left.columns)}")
        logger.info(f"Right DataFrame shape: {df_right.shape}, columns: {list(df_right.columns)}")
        
        # Check for potential matches
        left_keys = df_left[on_fields].drop_duplicates()
        right_keys = df_right[on_fields].drop_duplicates()
        merged_keys = pd.merge(left_keys, right_keys, on=on_fields, how='inner')
        logger.info(f"Number of matching join key combinations: {len(merged_keys)} out of {len(left_keys)} left keys")
        
        result = pd.merge(df_left, df_right, on=on_fields, how=args.how)
        logger.info(f"Result DataFrame shape: {result.shape}, columns: {list(result.columns)}")
        
        # # Apply limit if specified
        # if args.limit is not None and args.limit > 0:
        #     result = result.head(args.limit)
        #     logger.debug("Applied limit: %d", args.limit)
        
        # Log if no matches found
        if len(merged_keys) == 0:
            logger.warning("No matching join keys found between left and right datasets. All right-side columns will be None/NaN.")
        
        return result