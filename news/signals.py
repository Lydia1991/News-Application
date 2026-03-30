"""
signals.py - Django signals for the News Application.

Uses post_save on Article to detect when an article transitions from
unapproved to approved, then:
  1. Emails all relevant subscribers.
  2. POSTs the approval event to the internal /api/approved/ endpoint.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Article, CustomUser
from .utils import assign_role_group
from .utils import notify_subscribers, post_to_approved_api

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Article)
def on_article_post_save(sender, instance, created, **kwargs):
    """
    Triggered every time an Article is saved.

    We only act when:
      - The article is NOT newly created, AND
      - The 'approved' field has just been set to True.

    The pre-save state is tracked via a '_previously_approved' attribute
    set in the Article model's save() method override below.  If that
    attribute is absent (first-time saves), we compare against False as
    the safe default.
    """
    # Determine the previous approval state stored before the save
    was_approved_before = getattr(instance, '_previously_approved', False)

    # Only proceed when approval status changes from False → True
    if not created and instance.approved and not was_approved_before:
        logger.info(
            'Article "%s" (pk=%s) was just approved – triggering notifications.',
            instance.title,
            instance.pk,
        )

        # Step 1: Send notification emails to subscribers
        notify_subscribers(instance)

        # Step 2: POST to the internal /api/approved/ endpoint
        # No request context available in a signal, so we use the default URL
        post_to_approved_api(instance)


@receiver(post_save, sender=CustomUser)
def on_user_post_save(sender, instance, created, **kwargs):
    """Ensure each user belongs to the Django group that matches their role.

    Skips group sync when the save only touches fields other than 'role'
    """
    if kwargs.get('raw', False):
        return

    update_fields = kwargs.get('update_fields')
    # If update_fields is specified and 'role' is not among them, skip.
    if update_fields is not None and 'role' not in update_fields:
        return

    assign_role_group(instance)
