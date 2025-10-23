import logging
from django.apps import apps
from search2.models import SavedSearch
from search2.engine.core import run_pipeline

logger = logging.getLogger(__name__)

class RunSavedSearchCommand:
    name = "run_saved_search"

    def add_arguments(self, p):
        p.add_argument("name", help="Name of the SavedSearch to run")
        p.add_argument("--events", default=None, help="Optional events data to pass to pipeline")
        p.add_argument("--request", default=None, help="Optional request object")

    def run_none(self, data, args, ctx):
        return self._run(data, args, ctx)

    def run_qs(self, qs, args, ctx):
        return self._run(qs, args, ctx)

    def run_df(self, df, args, ctx):
        return self._run(df, args, ctx)

    def run_records(self, rows, args, ctx):
        return self._run(rows, args, ctx)

    def _run(self, data, args, ctx):
        try:
            saved_search = SavedSearch.objects.get(name=args.name)
        except SavedSearch.DoesNotExist:
            logger.error(f"SavedSearch with name '{args.name}' does not exist.")
            raise ValueError(f"SavedSearch with name '{args.name}' does not exist.")
        query = saved_search.query
        # If events are provided, use them as the first argument
        if args.events:
            data = args.events
        return run_pipeline(data, query, request=ctx.request)
