from rest_framework import serializers
from .models import SavedSearch

class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'name', 'query', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
