from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import SavedSearch

class SavedSearchSerializer(serializers.ModelSerializer):
    shared_with = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=get_user_model().objects.all(),
        required=False,
    )

    class Meta:
        model = SavedSearch
        fields = ['id', 'name', 'query', 'shared_with', 'is_public', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
