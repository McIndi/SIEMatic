import logging
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
        request = getattr(ctx, "request", None)
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            raise ValueError("run_saved_search requires an authenticated user context.")

        visible_searches = SavedSearch.objects.visible_to(user).filter(name=args.name).distinct()
        owned_searches = list(visible_searches.filter(owner=user))
        if owned_searches:
            if len(owned_searches) > 1:
                raise ValueError(
                    f"Multiple owned SavedSearch objects named '{args.name}' exist. "
                    "Rename one of them or run a more specific search."
                )
            saved_search = owned_searches[0]
        else:
            accessible_searches = list(visible_searches.exclude(owner=user))
            if not accessible_searches:
                logger.error("SavedSearch with name '%s' is not visible to %s.", args.name, user)
                raise ValueError(f"SavedSearch with name '{args.name}' does not exist or is not shared with you.")
            if len(accessible_searches) > 1:
                raise ValueError(
                    f"Multiple shared or public SavedSearch objects named '{args.name}' are visible to you. "
                    "Ask an owner to rename one of them."
                )
            saved_search = accessible_searches[0]

        query = saved_search.query
        # If events are provided, use them as the first argument
        if args.events:
            data = args.events
        return run_pipeline(data, query, request=ctx.request)
