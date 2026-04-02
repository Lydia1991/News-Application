"""
utils.py - Helper utilities for the News Application.

Provides:
  - assign_role_group(): assigns a user to the correct Django group/permissions
    based on their role.
  - get_article_subscribers(): collects email addresses of all subscribers
    for a given article (readers subscribed to the journalist or publisher).
  - notify_subscribers(): sends a notification email to all subscribers.
  - post_to_api(): sends a POST request to /api/approved/ to log an approval.
"""

import logging
from datetime import datetime, timezone

import requests
from django.contrib.auth.models import Group, Permission

from .models import Role

logger = logging.getLogger(__name__)


def generate_weather_story(location='Harare'):
    """
    Build an automatic weather story snippet for the given location.

    Uses Open-Meteo geocoding + forecast endpoints (no API key required).

    Parameters
    ----------
    location : str, optional
        The location (city name) for which to generate the weather story. Defaults to 'Harare'.

    Returns
    -------
    str or None
        Human-readable weather summary, or None if data cannot be fetched.

    Raises
    ------
    requests.RequestException
        If there is a network or API error (caught internally, returns None).
    """
    if not location:
        location = 'Harare'

    weather_code_map = {
        0: 'Clear sky',
        1: 'Mainly clear',
        2: 'Partly cloudy',
        3: 'Overcast',
        45: 'Fog',
        48: 'Depositing rime fog',
        51: 'Light drizzle',
        53: 'Moderate drizzle',
        55: 'Dense drizzle',
        61: 'Slight rain',
        63: 'Moderate rain',
        65: 'Heavy rain',
        71: 'Slight snow fall',
        73: 'Moderate snow fall',
        75: 'Heavy snow fall',
        80: 'Rain showers',
        95: 'Thunderstorm',
    }

    try:
        geo_response = requests.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': location, 'count': 1, 'language': 'en', 'format': 'json'},
            timeout=8,
        )
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        results = geo_data.get('results') or []
        if not results:
            return None

        hit = results[0]
        latitude = hit.get('latitude')
        longitude = hit.get('longitude')
        resolved_name = hit.get('name') or location
        country = hit.get('country') or ''

        weather_response = requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude': latitude,
                'longitude': longitude,
                'current': 'temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code',
                'timezone': 'auto',
            },
            timeout=8,
        )
        weather_response.raise_for_status()
        current = weather_response.json().get('current', {})

        weather_code = current.get('weather_code')
        condition = weather_code_map.get(weather_code, 'Variable conditions')
        temperature = current.get('temperature_2m')
        feels_like = current.get('apparent_temperature')
        humidity = current.get('relative_humidity_2m')
        wind_speed = current.get('wind_speed_10m')

        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        location_label = f'{resolved_name}, {country}'.strip(', ')

        return (
            f'Automatic weather update for {location_label} ({timestamp}).\n'
            f'Conditions: {condition}. Temperature: {temperature} C '
            f'(feels like {feels_like} C). Humidity: {humidity}%. '
            f'Wind speed: {wind_speed} km/h.'
        )
    except requests.RequestException as exc:
        logger.warning('Weather auto-update failed for "%s": %s', location, exc)
        return None


def _get_or_create_group_with_permissions(group_name, codenames):
    """
    Return (or create) a Django Group and assign the specified permissions.

    Parameters
    ----------
    group_name : str
        Human-readable name for the group (e.g. 'Editor').
    codenames : list[str]
        Permission codenames to assign (e.g. ['view_article', 'change_article']).

    Returns
    -------
    Group
        The created or updated Django Group instance.
    """
    group, _ = Group.objects.get_or_create(name=group_name)

    # Resolve permission set and replace current group permissions so the
    # mapping remains exactly aligned with project requirements.
    permissions = []
    for codename in codenames:
        try:
            perm = Permission.objects.get(codename=codename)
            permissions.append(perm)
        except Permission.DoesNotExist:
            logger.warning('Permission "%s" not found – skipping.', codename)

    group.permissions.set(permissions)

    return group


def has_group(user, group_name):
    """
    Return True when the authenticated user belongs to a Django group.

    Parameters
    ----------
    user : User
        The user to check.
    group_name : str
        The group name to check for membership.

    Returns
    -------
    bool
        True if the user is in the group, False otherwise.
    """
    return bool(
        user
        and user.is_authenticated
        and user.groups.filter(name=group_name).exists()
    )


def can_act_as_reader(user):
    """
    Check if the user can act as a reader (by role or group).

    Parameters
    ----------
    user : User
        The user to check.

    Returns
    -------
    bool
        True if the user is a reader, False otherwise.
    """
    return bool(user and user.is_authenticated and (user.role == Role.READER or has_group(user, 'Reader')))


def can_act_as_journalist(user):
    """
    Check if the user can act as a journalist (by role or group).

    Parameters
    ----------
    user : User
        The user to check.

    Returns
    -------
    bool
        True if the user is a journalist, False otherwise.
    """
    return bool(user and user.is_authenticated and (user.role == Role.JOURNALIST or has_group(user, 'Journalist')))


def can_act_as_editor(user):
    """
    Check if the user can act as an editor (by role or group).

    Parameters
    ----------
    user : User
        The user to check.

    Returns
    -------
    bool
        True if the user is an editor, False otherwise.
    """
    return bool(user and user.is_authenticated and (user.role == Role.EDITOR or has_group(user, 'Editor')))


def setup_groups():
    """
    Create (or update) the three role-based groups with correct permissions.

    Call this once during app startup via AppConfig.ready() or via a
    management command / migration.
    """
    # Permissions for Article and Newsletter models
    article_view   = 'view_article'
    article_add    = 'add_article'
    article_change = 'change_article'
    article_delete = 'delete_article'

    newsletter_view   = 'view_newsletter'
    newsletter_add    = 'add_newsletter'
    newsletter_change = 'change_newsletter'
    newsletter_delete = 'delete_newsletter'

    _get_or_create_group_with_permissions(
        'Reader',
        [article_view, newsletter_view],
    )

    _get_or_create_group_with_permissions(
        'Editor',
        [
            article_view, article_change, article_delete,
            newsletter_view, newsletter_change, newsletter_delete,
        ],
    )

    _get_or_create_group_with_permissions(
        'Journalist',
        [
            article_view, article_add, article_change, article_delete,
            newsletter_view, newsletter_add, newsletter_change, newsletter_delete,
        ],
    )


def assign_role_group(user):
    """
    Add a user to the Django group that matches their role.

    Also removes stale group memberships from previous roles.

    Parameters
    ----------
    user : User
        The user to assign to the correct group.
    """
    # Map Role constants to group names
    role_to_group = {
        Role.READER:     'Reader',
        Role.JOURNALIST: 'Journalist',
        Role.EDITOR:     'Editor',
    }

    target_group_name = role_to_group.get(user.role)
    if not target_group_name:
        logger.warning('Unknown role "%s" for user "%s".', user.role, user.username)
        return

    # Ensure groups exist before trying to add the user
    setup_groups()

    # Remove the user from all role groups and re-add to the correct one
    for group_name in role_to_group.values():
        group = Group.objects.get(name=group_name)
        user.groups.remove(group)

    target_group = Group.objects.get(name=target_group_name)
    user.groups.add(target_group)


def get_article_subscribers(article):
    """
    Return a list of unique email addresses for all subscribers of the given
    article (based on journalist subscription or publisher subscription).

    Parameters
    ----------
    article : Article
        The approved article whose subscribers should be notified.

    Returns
    -------
    list[str]
        Deduplicated list of subscriber email addresses.
    """
    from .models import CustomUser  # Imported here to avoid circular import

    emails = set()

    # Readers subscribed to the article's author (journalist)
    journalist_subscribers = CustomUser.objects.filter(
        subscribed_journalists=article.author,
        email__isnull=False,
    ).exclude(email='')

    for reader in journalist_subscribers:
        emails.add(reader.email)

    # Readers subscribed to the publisher (if the article has one)
    if article.publisher:
        publisher_subscribers = CustomUser.objects.filter(
            subscribed_publishers=article.publisher,
            email__isnull=False,
        ).exclude(email='')

        for reader in publisher_subscribers:
            emails.add(reader.email)

    return list(emails)


def notify_subscribers(article):
    """
    Send a notification email to all subscribers of the given article.

    Parameters
    ----------
    article : Article
        The newly approved article to notify subscribers about.

    Raises
    ------
    Exception
        If sending email fails (logged, not raised).
    """
    from django.core.mail import send_mail
    from django.conf import settings

    subscriber_emails = get_article_subscribers(article)

    if not subscriber_emails:
        logger.info('No subscribers to notify for article "%s".', article.title)
        return

    subject = f'New Article Published: {article.title}'
    body = (
        f'Hello,\n\n'
        f'A new article has been published:\n\n'
        f'Title: {article.title}\n'
        f'Author: {article.author.get_full_name() or article.author.username}\n'
    )

    if article.publisher:
        body += f'Publisher: {article.publisher.name}\n'

    body += (
        f'\n{article.content[:200]}...\n\n'
        f'Visit the website to read the full article.\n\n'
        f'Regards,\nThe News Application Team'
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=subscriber_emails,
            fail_silently=False,
        )
        logger.info(
            'Notification sent to %d subscriber(s) for article "%s".',
            len(subscriber_emails),
            article.title,
        )
    except Exception as exc:
        logger.error(
            'Failed to send notification for article "%s": %s',
            article.title,
            exc,
        )


def post_to_approved_api(article, request=None):
    """
    Send a POST request to the internal /api/approved/ endpoint to log the
    newly approved article.

    Parameters
    ----------
    article : Article
        The approved article to be logged.
    request : HttpRequest, optional
        Used to build the absolute URL. When called from a signal (no
        request context), falls back to localhost.

    Raises
    ------
    requests.RequestException
        If the POST request fails (logged, not raised).
    """
    if request is not None:
        base_url = request.build_absolute_uri('/api/approved/')
    else:
        base_url = 'http://127.0.0.1:8000/api/approved/'

    payload = {'article': article.pk, 'notes': 'Auto-logged on approval by signal.'}

    try:
        response = requests.post(
            base_url,
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        logger.info(
            'Article "%s" successfully logged to /api/approved/ (status %s).',
            article.title,
            response.status_code,
        )
    except requests.exceptions.RequestException as exc:
        logger.error(
            'Failed to POST article "%s" to /api/approved/: %s',
            article.title,
            exc,
        )
