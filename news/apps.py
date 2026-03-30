"""
apps.py - Application configuration for the 'news' app.

Connects Django signals when the application is ready so that article
approval events trigger subscriber notifications and API logging.
"""

import logging

from django.apps import AppConfig


logger = logging.getLogger(__name__)


class NewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news'

    def ready(self):
        """
        Import signals module to register all signal handlers.
        Groups are created via the post_migrate signal to avoid accessing
        the database during app initialisation (which causes a RuntimeWarning).
        """
        # Import signals to register them with Django's signal dispatcher
        import news.signals  # noqa: F401

        # Connect group-creation to the post_migrate signal so it runs
        # only after the database schema is fully set up.
        from django.db.models.signals import post_migrate

        def create_groups(sender, **kwargs):
            """Create role-based permission groups after migrations complete."""
            try:
                from news.utils import setup_groups
                setup_groups()
            except Exception as exc:
                logger.warning('Role-group setup after migration failed: %s', exc)

        post_migrate.connect(create_groups, sender=self, dispatch_uid='news.create_groups_post_migrate')
