"""
serializers.py - Django REST Framework serializers for the News Application.

Provides serialization for Article and ApprovedArticleLog models,
used by the /api/approved/ endpoint.
"""

from rest_framework import serializers

from .models import ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher, Tag


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user details exposed through API responses.

    Fields
    ------
    id : int
        User ID.
    username : str
        Username of the user.
    email : str
        Email address of the user.
    role : str
        Role of the user (reader, journalist, editor).
    """
     
class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'role']
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """
    Serializer for Publisher model.

    Fields
    ------
    id : int
        Publisher ID.
    name : str
        Name of the publisher.
    description : str
        Description of the publisher.
    created_at : datetime
        Timestamp when the publisher was created.
    """

    class Meta:
        model = Publisher
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class NewsletterSerializer(serializers.ModelSerializer):
    """
    Serializer for Newsletter model with nested author details.

    Fields
    ------
    id : int
        Newsletter ID.
    title : str
        Title of the newsletter.
    description : str
        Description of the newsletter.
    created_at : datetime
        Timestamp when the newsletter was created.
    author : UserSerializer
        Author of the newsletter (read-only).
    article_ids : list[int]
        IDs of articles included in the newsletter.
    """

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
    """
    Serializer for Article model used by the article REST API.

    Fields
    ------
    id : int
        Article ID.
    title : str
        Title of the article.
    content : str
        Main content of the article.
    author : int
        ID of the author (journalist).
    author_username : str
        Username of the author (read-only).
    publisher : int or None
        ID of the publisher (optional).
    publisher_name : str or None
        Name of the publisher (read-only).
    section : str
        Section/category of the article.
    section_display : str
        Human-readable section name (read-only).
    status : str
        Status of the article.
    status_display : str
        Human-readable status (read-only).
    weather_location : str
        Location for weather articles.
    story_image : Image
        Optional image for the article.
    tag_ids : list[int]
        IDs of tags associated with the article.
    tag_names : list[str]
        Names of tags (read-only).
    approved : bool
        Whether the article is approved.
    editor_feedback : str
        Feedback from the editor.
    created_at : datetime
        When the article was created.
    updated_at : datetime
        When the article was last updated.
    approved_at : datetime or None
        When the article was approved.
    """

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
        """
        Create an article owned by the authenticated journalist.

        Parameters
        ----------
        validated_data : dict
            Validated data for the new article.

        Returns
        -------
        Article
            The created Article instance.
        """
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

    Fields
    ------
    id : int
        Log entry ID.
    article : int
        ID of the approved article.
    article_detail : ArticleSerializer
        Nested article details (read-only).
    logged_at : datetime
        When the approval event was logged.
    notes : str
        Optional notes about the approval event.
    """

    # Nested article info for reads
    article_detail = ArticleSerializer(source='article', read_only=True)

    class Meta:
        model = ApprovedArticleLog
        fields = ['id', 'article', 'article_detail', 'logged_at', 'notes']
        read_only_fields = ['id', 'logged_at', 'article_detail']

    def validate_article(self, article):
        """
        Ensure the referenced article is actually approved before logging.

        Parameters
        ----------
        article : Article
            The article to validate.

        Returns
        -------
        Article
            The validated article instance.

        Raises
        ------
        serializers.ValidationError
            If the article is not approved.
        """
        if not article.approved:
            raise serializers.ValidationError(
                'Cannot log an unapproved article.'
            )
        return article
