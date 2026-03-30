"""
models.py - Data models for the News Application.

Defines CustomUser, Publisher, Article, Newsletter, and
ApprovedArticleLog (used by the REST API to persist approval events).
"""

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# Role constants – stored as a string on each user record
# ---------------------------------------------------------------------------
class Role(models.TextChoices):
    READER = 'reader', 'Reader'
    JOURNALIST = 'journalist', 'Journalist'
    EDITOR = 'editor', 'Editor'


# ---------------------------------------------------------------------------
# CustomUser
# ---------------------------------------------------------------------------
class CustomUser(AbstractUser):
    """
    Extended user model.

    All users have a 'role' field.  Reader-specific and journalist-specific
    fields co-exist on the same table; the application enforces that only
    the relevant subset is populated (the other set is NULL/empty).
    """

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.READER,
    )

    # -----------------------------------------------------------------------
    # Reader-only fields
    # -----------------------------------------------------------------------
    # Publishers the reader has subscribed to
    subscribed_publishers = models.ManyToManyField(
        'Publisher',
        blank=True,
        related_name='subscribers',
        help_text='Publications this reader subscribes to.',
    )

    # Journalists the reader has subscribed to
    subscribed_journalists = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='reader_subscribers',
        limit_choices_to={'role': Role.JOURNALIST},
        help_text='Individual journalists this reader subscribes to.',
    )

    # Override the default groups / user_permissions reverse accessors to
    # avoid clashes with the built-in auth.User model.
    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name='custom_users',
        help_text='Groups this user belongs to.',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name='custom_users',
        help_text='Specific permissions for this user.',
    )

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    def is_reader(self):
        """Return True if this user has the Reader role."""
        return self.role == Role.READER

    def is_journalist(self):
        """Return True if this user has the Journalist role."""
        return self.role == Role.JOURNALIST

    def is_editor(self):
        """Return True if this user has the Editor role."""
        return self.role == Role.EDITOR

    def save(self, *args, **kwargs):
        """
        Persist the user and enforce role-field consistency.

        Reader subscription fields are only meaningful for Reader users.
        If the user role is Journalist or Editor, these many-to-many
        relations are cleared to satisfy the project rule.
        """
        super().save(*args, **kwargs)

        if self.role != Role.READER:
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------
class Publisher(models.Model):
    """
    A curated publication that can have multiple editors and journalists.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Editors and journalists affiliated with this publisher
    editors = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='publisher_editor',
        limit_choices_to={'role': Role.EDITOR},
    )
    journalists = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='publisher_journalist',
        limit_choices_to={'role': Role.JOURNALIST},
    )

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------
class Tag(models.Model):
    """Lightweight label used to organize and relate articles."""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:50] or 'tag'
            slug = base_slug
            counter = 2
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'[:60]
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------
class Article(models.Model):
    """
    A news article written by a journalist.

    An article is either:
      - An independent article (publisher is NULL, author is the journalist).
      - A publisher article (publisher is set).
    """

    title = models.CharField(max_length=300)
    content = models.TextField()

    class Section(models.TextChoices):
        POLITICS = 'politics', 'Politics'
        TRENDING = 'trending', 'Trending'
        SPORTS = 'sports', 'Sports'
        SOCIAL_MEDIA = 'social_media', 'Social Media'
        WEATHER = 'weather', 'Weather'
        RELIGION = 'religion', 'Religion'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING_REVIEW = 'pending_review', 'Pending Review'
        PUBLISHED = 'published', 'Published'

    section = models.CharField(
        max_length=20,
        choices=Section.choices,
        default=Section.TRENDING,
    )

    story_image = models.ImageField(
        upload_to='article_images/',
        null=True,
        blank=True,
    )
    weather_location = models.CharField(
        max_length=120,
        blank=True,
        help_text='Optional location for auto-generated weather updates.',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='articles',
    )

    # The journalist who authored the article
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='articles',
        limit_choices_to={'role': Role.JOURNALIST},
    )

    # Optional link to a publisher (NULL for independent articles)
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Set to True by an editor when the article is approved for publishing
    approved = models.BooleanField(default=False)

    # The editor who approved the article (NULL until approved)
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_articles',
        limit_choices_to={'role': Role.EDITOR},
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    editor_feedback = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        """
        Enforce the business rule that an article must be linked to at least
        one publishing source: an independent journalist author or a publisher.
        """
        # During form validation on create, author is assigned in the view via
        # commit=False after form.is_valid(). Skip this check before the first
        # save to avoid blocking legitimate journalist submissions.
        if self.pk and self.author_id is None and self.publisher_id is None:
            raise ValidationError('An article must have either an author or a publisher.')

    def save(self, *args, **kwargs):
        """
        Override save() to record the pre-save approval state on the instance.
        The post_save signal reads this attribute to decide whether the article
        just transitioned from unapproved → approved.
        """
        if self.approved and self.status != Article.Status.PUBLISHED:
            self.status = Article.Status.PUBLISHED
        elif not self.approved and self.status == Article.Status.PUBLISHED:
            self.status = Article.Status.PENDING_REVIEW

        self.approved = self.status == Article.Status.PUBLISHED

        if self.pk:
            # Fetch the current database value before writing the update
            try:
                previous = Article.objects.get(pk=self.pk)
                self._previously_approved = previous.approved
            except Article.DoesNotExist:
                self._previously_approved = False
        else:
            # Brand-new article – there is no previous state
            self._previously_approved = False

        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Newsletter
# ---------------------------------------------------------------------------
class Newsletter(models.Model):
    """
    A curated collection of articles assembled by a journalist.
    """

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # The journalist (or editor) who created the newsletter
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='newsletters',
        limit_choices_to={
            'role__in': [Role.JOURNALIST, Role.EDITOR],
        },
    )

    # Articles included in this newsletter
    articles = models.ManyToManyField(
        Article,
        blank=True,
        related_name='newsletters',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        """Only journalists and editors can author newsletters."""
        # author_id may be None when the form validates before setting commit=False
        if not self.author_id:
            return
        if self.author.role not in {Role.JOURNALIST, Role.EDITOR}:
            raise ValidationError('Only journalists and editors can author newsletters.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# ApprovedArticleLog  (used by the REST API)
# ---------------------------------------------------------------------------
class ApprovedArticleLog(models.Model):
    """
    Persists each article-approval event received by the /api/approved/
    endpoint.  This simulates an external system logging approved content.
    """

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='approval_logs',
    )
    logged_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'Log for "{self.article.title}" at {self.logged_at}'
