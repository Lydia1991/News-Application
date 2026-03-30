"""
admin.py - Django admin site configuration for the News Application.

Registers all models with custom admin classes to improve usability
in the admin panel.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher, Tag


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin configuration for the custom user model."""

    # Show role in the user list
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter  = ('role', 'is_staff', 'is_active', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    # Add the 'role' field to the existing UserAdmin fieldsets
    fieldsets = UserAdmin.fieldsets + (
        ('News App Role', {
            'fields': ('role', 'subscribed_publishers', 'subscribed_journalists'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('News App Role', {
            'fields': ('role',),
        }),
    )


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    """Admin configuration for Publisher."""

    list_display  = ('name', 'created_at')
    search_fields = ('name',)
    filter_horizontal = ('editors', 'journalists')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin configuration for Article."""

    list_display  = ('title', 'author', 'publisher', 'status', 'approved', 'created_at')
    list_filter   = ('status', 'approved', 'publisher', 'section')
    search_fields = ('title', 'author__username')
    date_hierarchy = 'created_at'
    readonly_fields = ('approved_at', 'approved_by')
    filter_horizontal = ('tags',)

    actions = ['approve_articles']

    @admin.action(description='Approve selected articles')
    def approve_articles(self, request, queryset):
        """Bulk-approve selected articles from the admin panel."""
        from django.utils import timezone
        updated = 0
        for article in queryset.filter(approved=False):
            article.status = Article.Status.PUBLISHED
            article.approved_by = request.user
            article.approved_at = timezone.now()
            article.save()  # Triggers post_save signal
            updated += 1
        self.message_user(request, f'{updated} article(s) approved.')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin configuration for article tags."""

    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Admin configuration for Newsletter."""

    list_display  = ('title', 'author', 'created_at')
    search_fields = ('title', 'author__username')
    filter_horizontal = ('articles',)


@admin.register(ApprovedArticleLog)
class ApprovedArticleLogAdmin(admin.ModelAdmin):
    """Admin configuration for ApprovedArticleLog (read-only)."""

    list_display  = ('article', 'logged_at', 'notes')
    readonly_fields = ('article', 'logged_at', 'notes')

    def has_add_permission(self, request):
        return False  # Logs are created only through the API

    def has_change_permission(self, request, obj=None):
        return False  # Logs are immutable
