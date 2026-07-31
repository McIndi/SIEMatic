from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import permissions, serializers, viewsets
from drf_spectacular.utils import extend_schema

from search2.engine.core import run_pipeline
from search2.utils import coerce_to_list_of_dicts
from .models import SavedSearch
from .serializers import SavedSearchSerializer


class SearchRunRequestSerializer(serializers.Serializer):
    query = serializers.CharField()


class SearchRunMetaSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class SearchRunResponseSerializer(serializers.Serializer):
    rows = serializers.ListField(child=serializers.DictField())
    meta = SearchRunMetaSerializer()


class SearchRunErrorSerializer(serializers.Serializer):
    error = serializers.CharField()


class Search2RunView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'search'

    @extend_schema(
        request=SearchRunRequestSerializer,
        responses={200: SearchRunResponseSerializer, 400: SearchRunErrorSerializer},
    )
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
    queryset = SavedSearch.objects.all()
    serializer_class = SavedSearchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.action in {'update', 'partial_update', 'destroy'}:
            return SavedSearch.objects.filter(owner=self.request.user)
        return SavedSearch.objects.visible_to(self.request.user).order_by('name')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
