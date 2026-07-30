from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, permissions

from search2.engine.core import run_pipeline
from search2.utils import coerce_to_list_of_dicts
from .models import SavedSearch
from .serializers import SavedSearchSerializer

class Search2RunView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'search'

    def post(self, request):
        query = request.data.get("query", "")
        try:
            result = run_pipeline(None, query, request=request)
            rows = coerce_to_list_of_dicts(result)
            return Response({"rows": rows, "meta": {"count": len(rows)}})
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"[search2 API] Error occurred while running pipeline: {e}")
            return Response({"error": str(e)}, status=400)

class SavedSearchViewSet(viewsets.ModelViewSet):
    serializer_class = SavedSearchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.action in {'update', 'partial_update', 'destroy'}:
            return SavedSearch.objects.filter(owner=self.request.user)
        return SavedSearch.objects.visible_to(self.request.user).order_by('name')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
