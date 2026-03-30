"""
serializers.py - Django REST Framework serializers for the News Application.

Provides serialization for Article and ApprovedArticleLog models,
used by the /api/approved/ endpoint.
"""

from rest_framework import serializers

from .models import ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher, Tag


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details exposed through API responses."""

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'role']
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """Serializer for Publisher model."""

    class Meta:
        model = Publisher
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class NewsletterSerializer(serializers.ModelSerializer):
    """Serializer for Newsletter model with nested author details."""

    author = UserSerializer(read_only=True)
    article_ids = serializers.PrimaryKeyRelatedField(
        source='articles',
        many=True,
        queryset=Article.objects.filter(approved=True),
        required=False,
    )

    class Meta:
        model = Newsletter
        fields = [
            'id',
            'title',
            'description',
            'created_at',
            'author',
            'article_ids',
        ]
        read_only_fields = ['id', 'created_at', 'author']


class ArticleSerializer(serializers.ModelSerializer):
    """Serializer for Article model used by the article REST API."""

    author_username = serializers.CharField(source='author.username', read_only=True)
    publisher_name = serializers.CharField(source='publisher.name', read_only=True, allow_null=True)
    section_display = serializers.CharField(source='get_section_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    tag_names = serializers.StringRelatedField(source='tags', many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source='tags',
        many=True,
        queryset=Tag.objects.all(),
        required=False,
    )

    class Meta:
        model = Article
        fields = [
            'id',
            'title',
            'content',
            'author',
            'author_username',
            'publisher',
            'publisher_name',
            'section',
            'section_display',
            'status',
            'status_display',
            'weather_location',
            'story_image',
            'tag_ids',
            'tag_names',
            'approved',
            'editor_feedback',
            'created_at',
            'updated_at',
            'approved_at',
        ]
        read_only_fields = [
            'id',
            'author',
            'author_username',
            'publisher_name',
            'status',
            'status_display',
            'approved',
            'editor_feedback',
            'created_at',
            'updated_at',
            'approved_at',
        ]

    def create(self, validated_data):
        """Create an article owned by the authenticated journalist."""
        request = self.context.get('request')
        validated_data['author'] = request.user
        validated_data['status'] = Article.Status.PENDING_REVIEW
        validated_data['approved'] = False
        return super().create(validated_data)


class ApprovedArticleLogSerializer(serializers.ModelSerializer):
    """
    Serializer for ApprovedArticleLog.

    On creation (POST), only 'article' and optional 'notes' are required.
    The nested article detail is returned on read (GET).
    """

    # Nested article info for reads
    article_detail = ArticleSerializer(source='article', read_only=True)

    class Meta:
        model = ApprovedArticleLog
        fields = ['id', 'article', 'article_detail', 'logged_at', 'notes']
        read_only_fields = ['id', 'logged_at', 'article_detail']

    def validate_article(self, article):
        """Ensure the referenced article is actually approved before logging."""
        if not article.approved:
            raise serializers.ValidationError(
                'Cannot log an unapproved article.'
            )
        return article
