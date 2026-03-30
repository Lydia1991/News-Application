"""
tests.py - Unit tests for the News Application.

Test coverage:
  1. Model tests (CustomUser, Publisher, Article, Newsletter, ApprovedArticleLog)
  2. Role-group assignment via assign_role_group()
  3. View access-control tests (authentication & authorisation)
  4. Article approval workflow (signal triggers, email, API log)
  5. REST API endpoint tests (/api/approved/)
  6. Subscription view tests
"""

from unittest.mock import patch
import tempfile

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    ApprovedArticleLog,
    Article,
    CustomUser,
    Newsletter,
    Publisher,
    Role,
    Tag,
)
from .utils import assign_role_group, get_article_subscribers, setup_groups


# ===========================================================================
# Helper factory methods
# ===========================================================================

def make_user(username, role=Role.READER, password='testpass123'):
    """Create and return a CustomUser with the given role."""
    user = CustomUser.objects.create_user(
        username=username,
        password=password,
        role=role,
        email=f'{username}@example.com',
    )
    assign_role_group(user)
    return user


def make_article(
    author,
    title='Test Article',
    approved=False,
    publisher=None,
    section='trending',
    status_value=None,
):
    """Create and return an Article."""
    return Article.objects.create(
        title=title,
        content='Article body content.',
        author=author,
        publisher=publisher,
        section=section,
        approved=approved,
        status=status_value or Article.Status.PENDING_REVIEW,
    )


# ===========================================================================
# 1. Model tests
# ===========================================================================

class CustomUserModelTest(TestCase):
    """Tests for the CustomUser model."""

    def test_create_reader(self):
        """A reader user is created with the correct role."""
        user = make_user('alice', role=Role.READER)
        self.assertEqual(user.role, Role.READER)
        self.assertTrue(user.is_reader())
        self.assertFalse(user.is_journalist())
        self.assertFalse(user.is_editor())

    def test_create_journalist(self):
        """A journalist user is created with the correct role."""
        user = make_user('bob', role=Role.JOURNALIST)
        self.assertEqual(user.role, Role.JOURNALIST)
        self.assertTrue(user.is_journalist())
        self.assertFalse(user.is_reader())

    def test_create_editor(self):
        """An editor user is created with the correct role."""
        user = make_user('charlie', role=Role.EDITOR)
        assertTrue = self.assertTrue
        assertTrue(user.is_editor())

    def test_user_str_representation(self):
        """__str__ returns username and role display."""
        user = make_user('diana', role=Role.JOURNALIST)
        self.assertIn('diana', str(user))
        self.assertIn('Journalist', str(user))

    def test_non_reader_roles_clear_reader_subscription_fields(self):
        """
        If a user changes from Reader to Journalist/Editor, reader-only
        subscription fields are cleared.
        """
        user = make_user('reader_to_journalist', role=Role.READER)
        journalist = make_user('target_journalist', role=Role.JOURNALIST)
        publisher = Publisher.objects.create(name='Role Switch Publication')

        user.subscribed_journalists.add(journalist)
        user.subscribed_publishers.add(publisher)
        self.assertEqual(user.subscribed_journalists.count(), 1)
        self.assertEqual(user.subscribed_publishers.count(), 1)

        user.role = Role.JOURNALIST
        user.save()

        self.assertEqual(user.subscribed_journalists.count(), 0)
        self.assertEqual(user.subscribed_publishers.count(), 0)


class PublisherModelTest(TestCase):
    """Tests for the Publisher model."""

    def setUp(self):
        self.editor = make_user('ed_user', role=Role.EDITOR)
        self.journalist = make_user('j_user', role=Role.JOURNALIST)
        self.publisher = Publisher.objects.create(
            name='Tech Weekly',
            description='A tech publication.',
        )

    def test_publisher_str(self):
        """Publisher __str__ returns its name."""
        self.assertEqual(str(self.publisher), 'Tech Weekly')

    def test_add_editor_to_publisher(self):
        """An editor can be affiliated with a publisher."""
        self.publisher.editors.add(self.editor)
        self.assertIn(self.editor, self.publisher.editors.all())

    def test_add_journalist_to_publisher(self):
        """A journalist can be affiliated with a publisher."""
        self.publisher.journalists.add(self.journalist)
        self.assertIn(self.journalist, self.publisher.journalists.all())


class ArticleModelTest(TestCase):
    """Tests for the Article model."""

    def setUp(self):
        self.journalist = make_user('j1', role=Role.JOURNALIST)
        self.editor = make_user('e1', role=Role.EDITOR)
        self.publisher = Publisher.objects.create(name='Model Test Publisher')

    def test_article_defaults_to_unapproved(self):
        """Newly created articles are unapproved by default."""
        article = make_article(self.journalist)
        self.assertFalse(article.approved)

    def test_article_str_returns_title(self):
        """Article __str__ returns its title."""
        article = make_article(self.journalist, title='My Article')
        self.assertEqual(str(article), 'My Article')

    def test_approval_sets_approved_flag(self):
        """Setting approved=True and saving marks the article approved."""
        article = make_article(self.journalist)
        article.approved = True
        article.approved_by = self.editor
        article.approved_at = timezone.now()
        article.save()
        article.refresh_from_db()
        self.assertTrue(article.approved)

    def test_previously_approved_attribute_on_save(self):
        """
        The save() override stores _previously_approved to help signals
        detect when approval status changes.
        """
        article = make_article(self.journalist)
        # Initial save: _previously_approved should be False
        self.assertFalse(article._previously_approved)
        # Approve the article
        article.approved = True
        article.save()
        # On the next save (already approved), _previously_approved should be True
        article.content = 'Updated content.'
        article.save()
        self.assertTrue(article._previously_approved)

    def test_clean_allows_publisher_without_author(self):
        """Model clean should not crash when author is unset but publisher is set."""
        article = Article(
            title='Publisher-backed draft',
            content='Draft body.',
            publisher=self.publisher,
            section='trending',
        )

        # Must not raise RelatedObjectDoesNotExist when clean() checks relations.
        article.clean()


class NewsletterModelTest(TestCase):
    """Tests for the Newsletter model."""

    def setUp(self):
        self.journalist = make_user('j_news', role=Role.JOURNALIST)
        self.article = make_article(self.journalist, approved=True)

    def test_create_newsletter(self):
        """A newsletter can be created and linked to articles."""
        nl = Newsletter.objects.create(
            title='Weekly Digest',
            description='Top stories.',
            author=self.journalist,
        )
        nl.articles.add(self.article)
        self.assertEqual(nl.articles.count(), 1)

    def test_newsletter_str_returns_title(self):
        """Newsletter __str__ returns its title."""
        nl = Newsletter.objects.create(
            title='Test Letter',
            author=self.journalist,
        )
        self.assertEqual(str(nl), 'Test Letter')


# ===========================================================================
# 2. Group assignment tests
# ===========================================================================

class RoleGroupAssignmentTest(TestCase):
    """Tests for assign_role_group() utility."""

    def test_reader_assigned_to_reader_group(self):
        """A reader user is placed in the Reader group."""
        user = make_user('r1', role=Role.READER)
        group_names = list(user.groups.values_list('name', flat=True))
        self.assertIn('Reader', group_names)
        self.assertNotIn('Editor', group_names)
        self.assertNotIn('Journalist', group_names)

    def test_journalist_assigned_to_journalist_group(self):
        """A journalist user is placed in the Journalist group."""
        user = make_user('j_grp', role=Role.JOURNALIST)
        group_names = list(user.groups.values_list('name', flat=True))
        self.assertIn('Journalist', group_names)

    def test_editor_assigned_to_editor_group(self):
        """An editor user is placed in the Editor group."""
        user = make_user('e_grp', role=Role.EDITOR)
        group_names = list(user.groups.values_list('name', flat=True))
        self.assertIn('Editor', group_names)

    def test_reassignment_removes_old_group(self):
        """
        Changing a user's role and re-running assign_role_group() moves
        them to the new group and removes the old one.
        """
        user = make_user('swap_user', role=Role.READER)
        self.assertIn('Reader', user.groups.values_list('name', flat=True))

        user.role = Role.JOURNALIST
        user.save()
        assign_role_group(user)

        group_names = list(user.groups.values_list('name', flat=True))
        self.assertIn('Journalist', group_names)
        self.assertNotIn('Reader', group_names)

    def test_group_permissions_match_project_spec(self):
        """Reader/Editor/Journalist group permissions match the requirement."""
        setup_groups()

        reader_group = Group.objects.get(name='Reader')
        editor_group = Group.objects.get(name='Editor')
        journalist_group = Group.objects.get(name='Journalist')

        reader_perms = set(reader_group.permissions.values_list('codename', flat=True))
        editor_perms = set(editor_group.permissions.values_list('codename', flat=True))
        journalist_perms = set(journalist_group.permissions.values_list('codename', flat=True))

        required_reader = {'view_article', 'view_newsletter'}
        required_editor = {
            'view_article', 'change_article', 'delete_article',
            'view_newsletter', 'change_newsletter', 'delete_newsletter',
        }
        required_journalist = {
            'add_article', 'view_article', 'change_article', 'delete_article',
            'add_newsletter', 'view_newsletter', 'change_newsletter', 'delete_newsletter',
        }

        self.assertEqual(reader_perms, required_reader)
        self.assertEqual(editor_perms, required_editor)
        self.assertEqual(journalist_perms, required_journalist)


# ===========================================================================
# 3. View access-control tests
# ===========================================================================

class AuthenticationViewTest(TestCase):
    """Tests for login, logout, and registration views."""

    def setUp(self):
        self.client = Client()
        self.reader = make_user('reader1', role=Role.READER)

    def test_login_page_loads(self):
        """The login page returns HTTP 200."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'news/login.html')

    def test_register_page_loads(self):
        """The registration page returns HTTP 200."""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_valid_login(self):
        """A user with correct credentials is logged in and redirected."""
        response = self.client.post(reverse('login'), {
            'username': 'reader1',
            'password': 'testpass123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_valid_login_with_news_specific_field_names(self):
        """The login view accepts the news-specific form field names."""
        response = self.client.post(reverse('login'), {
            'news_username': 'reader1',
            'news_password': 'testpass123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_invalid_login_shows_error(self):
        """Wrong credentials display an error on the login page."""
        response = self.client.post(reverse('login'), {
            'username': 'reader1',
            'password': 'wrong_password',
        })
        self.assertContains(response, 'Invalid username or password')

    def test_logout_redirects_to_login(self):
        """Logging out redirects the user to the login page."""
        self.client.login(username='reader1', password='testpass123')
        response = self.client.get(reverse('logout'), follow=True)
        self.assertRedirects(response, reverse('login'))


class ArticleAccessControlTest(TestCase):
    """Tests that ensure access control is enforced on article views."""

    def setUp(self):
        self.client = Client()
        self.journalist = make_user('journ', role=Role.JOURNALIST)
        self.editor = make_user('ed', role=Role.EDITOR)
        self.reader = make_user('rdr', role=Role.READER)
        self.article = make_article(self.journalist, approved=False)

    def test_reader_cannot_view_pending_article(self):
        """Readers are redirected when trying to view an unapproved article."""
        self.client.login(username='rdr', password='testpass123')
        response = self.client.get(
            reverse('article_detail', args=[self.article.pk]), follow=True
        )
        self.assertRedirects(response, reverse('home'))

    def test_journalist_can_create_article(self):
        """Journalists can access the article creation view."""
        self.client.login(username='journ', password='testpass123')
        response = self.client.get(reverse('article_create'))
        self.assertEqual(response.status_code, 200)

    def test_reader_cannot_create_article(self):
        """Readers are redirected from the article creation view."""
        self.client.login(username='rdr', password='testpass123')
        response = self.client.get(reverse('article_create'), follow=True)
        self.assertRedirects(response, reverse('home'))

    def test_editor_can_view_pending_queue(self):
        """Editors can access the pending articles queue."""
        self.client.login(username='ed', password='testpass123')
        response = self.client.get(reverse('pending_articles'))
        self.assertEqual(response.status_code, 200)

    def test_reader_cannot_view_pending_queue(self):
        """Readers are redirected from the pending articles queue."""
        self.client.login(username='rdr', password='testpass123')
        response = self.client.get(reverse('pending_articles'), follow=True)
        self.assertRedirects(response, reverse('home'))

    def test_unauthenticated_user_redirected_from_create(self):
        """An unauthenticated user is redirected to the login page."""
        response = self.client.get(reverse('article_create'))
        self.assertIn('/login/', response.url)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_journalist_can_upload_story_image(self):
        """Journalist can upload a story image when creating an article."""
        self.client.login(username='journ', password='testpass123')

        image_file = SimpleUploadedFile(
            'story.gif',
            (
                b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,'
                b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
            ),
            content_type='image/gif',
        )

        response = self.client.post(
            reverse('article_create'),
            {
                'title': 'Image Story',
                'content': 'Story with image.',
                'section': 'trending',
                'weather_location': '',
                'publisher': '',
                'story_image': image_file,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        created = Article.objects.get(title='Image Story')
        self.assertTrue(bool(created.story_image))

    @patch('news.views.generate_weather_story')
    def test_weather_section_auto_generates_content(self, mock_weather):
        """Weather section article prepends auto-generated weather summary."""
        mock_weather.return_value = 'Automatic weather update for Harare.'

        self.client.login(username='journ', password='testpass123')
        response = self.client.post(
            reverse('article_create'),
            {
                'title': 'Weather Story',
                'content': 'Manual reporter notes.',
                'section': 'weather',
                'weather_location': 'Harare',
                'auto_weather_update': 'on',
                'publisher': '',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        created = Article.objects.get(title='Weather Story')
        self.assertEqual(created.weather_location, 'Harare')
        self.assertIn('Automatic weather update for Harare.', created.content)
        self.assertIn('Manual reporter notes.', created.content)

    @patch('news.views.generate_weather_story')
    def test_weather_section_manual_when_auto_toggle_off(self, mock_weather):
        """Weather section remains manual when auto weather toggle is disabled."""
        self.client.login(username='journ', password='testpass123')
        response = self.client.post(
            reverse('article_create'),
            {
                'title': 'Manual Weather Story',
                'content': 'Only manual weather analysis.',
                'section': 'weather',
                'weather_location': 'Harare',
                'publisher': '',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        created = Article.objects.get(title='Manual Weather Story')
        self.assertEqual(created.content, 'Only manual weather analysis.')
        mock_weather.assert_not_called()

    def test_reader_home_search_filters_visible_articles(self):
        """Reader search narrows the approved feed by keyword."""
        make_article(
            self.journalist,
            title='Election Special Analysis',
            approved=True,
            section='politics',
        )
        make_article(
            self.journalist,
            title='Sports Daily Bulletin',
            approved=True,
            section='sports',
        )

        self.client.login(username='rdr', password='testpass123')
        response = self.client.get(reverse('home'), {'q': 'Election'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Election Special Analysis')
        self.assertNotContains(response, 'Sports Daily Bulletin')

    def test_reader_home_hides_workflow_status_controls(self):
        """Readers do not see workflow status filters and status query is ignored."""
        make_article(
            self.journalist,
            title='Published Reader Story',
            approved=True,
            status_value=Article.Status.PUBLISHED,
        )

        self.client.login(username='rdr', password='testpass123')
        response = self.client.get(reverse('home'), {'status': Article.Status.DRAFT})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'All Statuses')
        self.assertNotContains(response, 'Status: Draft')
        self.assertContains(response, 'Published Reader Story')

    def test_reader_home_is_paginated(self):
        """Reader home feed paginates article listings."""
        for index in range(8):
            make_article(
                self.journalist,
                title=f'Reader Pagination Story {index}',
                approved=True,
                section='trending',
            )

        self.client.login(username='rdr', password='testpass123')
        page_one = self.client.get(reverse('home'))
        page_two = self.client.get(reverse('home'), {'page': 2})

        self.assertEqual(page_one.status_code, 200)
        self.assertTrue(page_one.context['is_paginated'])
        self.assertEqual(page_one.context['page_obj'].number, 1)

        self.assertEqual(page_two.status_code, 200)
        self.assertEqual(page_two.context['page_obj'].number, 2)

    def test_journalist_can_save_article_as_draft(self):
        """Journalists can explicitly save a draft instead of submitting review."""
        self.client.login(username='journ', password='testpass123')

        response = self.client.post(
            reverse('article_create'),
            {
                'title': 'Draft Story',
                'content': 'Draft content only.',
                'section': 'trending',
                'weather_location': '',
                'publisher': '',
                'save_draft': '1',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        created = Article.objects.get(title='Draft Story')
        self.assertEqual(created.status, Article.Status.DRAFT)
        self.assertFalse(created.approved)

    def test_editor_home_status_filter_shows_only_selected_status(self):
        """Editor can filter home feed by article workflow status."""
        make_article(
            self.journalist,
            title='Published Feed Story',
            approved=True,
            status_value=Article.Status.PUBLISHED,
        )
        make_article(
            self.journalist,
            title='Draft Feed Story',
            approved=False,
            status_value=Article.Status.DRAFT,
        )

        self.client.login(username='ed', password='testpass123')
        response = self.client.get(reverse('home'), {'status': Article.Status.DRAFT})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Draft Feed Story')
        self.assertNotContains(response, 'Published Feed Story')

    def test_pending_queue_status_filter_can_show_drafts(self):
        """Editor status filter on pending queue can switch from pending to drafts."""
        make_article(
            self.journalist,
            title='Draft Queue Story',
            approved=False,
            status_value=Article.Status.DRAFT,
        )

        self.client.login(username='ed', password='testpass123')
        response = self.client.get(reverse('pending_articles'), {'status': Article.Status.DRAFT})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Draft Queue Story')


class RelatedArticleViewTest(TestCase):
    """Tests related story suggestions in article detail context."""

    def setUp(self):
        self.client = Client()
        self.author = make_user('rel_author', role=Role.JOURNALIST)
        self.tech = Tag.objects.create(name='Tech')
        self.ai = Tag.objects.create(name='AI')

        self.primary = make_article(self.author, title='Primary Story', approved=True)
        self.primary.tags.add(self.tech, self.ai)

        self.related = make_article(self.author, title='Related Story', approved=True)
        self.related.tags.add(self.ai)

        self.unrelated = make_article(self.author, title='Unrelated Story', approved=True)

    def test_related_articles_prioritize_shared_tags(self):
        """Detail view context includes stories that share at least one tag."""
        response = self.client.get(reverse('article_detail', args=[self.primary.pk]))
        self.assertEqual(response.status_code, 200)

        related_titles = [item.title for item in response.context['related_articles']]
        self.assertIn('Related Story', related_titles)


# ===========================================================================
# 4. Article approval workflow tests
# ===========================================================================

class ArticleApprovalTest(TestCase):
    """Tests for the article approval view and signal workflow."""

    def setUp(self):
        self.client = Client()
        self.journalist = make_user('j_approve', role=Role.JOURNALIST)
        self.editor = make_user('e_approve', role=Role.EDITOR)
        self.reader = make_user('r_approve', role=Role.READER)
        self.article = make_article(self.journalist, approved=False)
        # Subscribe the reader to the journalist
        self.reader.subscribed_journalists.add(self.journalist)

    def test_editor_can_access_approve_page(self):
        """Editors can load the article approval confirmation page."""
        self.client.login(username='e_approve', password='testpass123')
        response = self.client.get(
            reverse('article_approve', args=[self.article.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_non_editor_cannot_approve(self):
        """Journalists and readers cannot access the approve view."""
        self.client.login(username='j_approve', password='testpass123')
        response = self.client.get(
            reverse('article_approve', args=[self.article.pk]),
            follow=True,
        )
        self.assertRedirects(
            response, reverse('article_detail', args=[self.article.pk])
        )

    def test_editor_group_member_can_approve(self):
        """Users assigned to Editor group can approve even if role is not editor."""
        group_editor = make_user('group_editor', role=Role.READER)
        editor_group = Group.objects.get(name='Editor')
        group_editor.groups.add(editor_group)

        self.client.login(username='group_editor', password='testpass123')
        response = self.client.post(reverse('article_approve', args=[self.article.pk]), follow=True)
        self.assertEqual(response.status_code, 200)

        self.article.refresh_from_db()
        self.assertTrue(self.article.approved)

    @patch('news.utils.notify_subscribers')
    @patch('news.utils.post_to_approved_api')
    def test_approval_marks_article_approved(self, mock_post, mock_notify):
        """
        POSTing to the approve view sets article.approved=True and stores
        the approving editor.
        """
        self.client.login(username='e_approve', password='testpass123')
        self.client.post(reverse('article_approve', args=[self.article.pk]))
        self.article.refresh_from_db()
        self.assertTrue(self.article.approved)
        self.assertEqual(self.article.approved_by, self.editor)
        mock_notify.assert_called_once_with(self.article)
        mock_post.assert_called_once()

    def test_approval_can_store_editor_feedback(self):
        """Editor feedback entered during approval is persisted on article."""
        self.client.login(username='e_approve', password='testpass123')
        self.client.post(
            reverse('article_approve', args=[self.article.pk]),
            {'editor_feedback': 'Great reporting. Keep the same source rigor.'},
        )

        self.article.refresh_from_db()
        self.assertEqual(self.article.status, Article.Status.PUBLISHED)
        self.assertIn('Great reporting', self.article.editor_feedback)

    def test_get_article_subscribers_returns_reader_emails(self):
        """
        get_article_subscribers returns the reader's email when they are
        subscribed to the article's journalist.
        """
        self.article.approved = True
        self.article.save()

        emails = get_article_subscribers(self.article)
        self.assertIn(self.reader.email, emails)

    def test_get_article_subscribers_includes_publisher_subscribers(self):
        """
        get_article_subscribers includes readers subscribed to the publisher
        when the article has a publisher.
        """
        publisher = Publisher.objects.create(name='Daily News')
        reader2 = make_user('r2_pub', role=Role.READER)
        reader2.subscribed_publishers.add(publisher)

        article2 = make_article(self.journalist, publisher=publisher, approved=True)
        emails = get_article_subscribers(article2)
        self.assertIn(reader2.email, emails)


# ===========================================================================
# 5. REST API tests for /api/approved/
# ===========================================================================

class ApprovedArticleAPITest(TestCase):
    """
    Tests for the ApprovedArticleLog REST API endpoint.

    These tests simulate calling the third-party integration endpoint and
    verify that approval events are correctly persisted.
    """

    def setUp(self):
        self.client = APIClient()
        self.journalist = make_user('j_api', role=Role.JOURNALIST)
        self.editor = make_user('e_api', role=Role.EDITOR)
        # Create an approved article to use in API calls
        self.article = make_article(self.journalist, approved=True)

    def test_get_approved_logs_unauthenticated(self):
        """
        Any user (including unauthenticated) can GET the list of approval logs.
        """
        response = self.client.get(reverse('api_approved'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_creates_log_entry(self):
        """
        An authenticated POST to /api/approved/ creates an ApprovedArticleLog.
        """
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(
            reverse('api_approved'),
            {'article': self.article.pk, 'notes': 'Test log entry.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ApprovedArticleLog.objects.count(), 1)
        self.assertEqual(ApprovedArticleLog.objects.first().article, self.article)

    def test_post_unauthenticated_allowed_for_internal_signal(self):
        """
        Unauthenticated POST to /api/approved/ is allowed for internal
        signal-triggered integration simulation.
        """
        response = self.client.post(
            reverse('api_approved'),
            {'article': self.article.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_unapproved_article_returns_400(self):
        """
        POSTing an unapproved article ID returns HTTP 400 (validation error).
        """
        unapproved = make_article(self.journalist, approved=False)
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(
            reverse('api_approved'),
            {'article': unapproved.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_response_contains_article_detail(self):
        """
        GET /api/approved/ returns nested article_detail in each log entry.
        """
        ApprovedArticleLog.objects.create(article=self.article, notes='auto')
        response = self.client.get(reverse('api_approved'))
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertIn('article_detail', data[0])
        self.assertEqual(data[0]['article_detail']['title'], self.article.title)


# ===========================================================================
# 6. Subscription view tests
# ===========================================================================

class SubscriptionViewTest(TestCase):
    """Tests for the subscription management view."""

    def setUp(self):
        self.client = Client()
        self.reader = make_user('sub_reader', role=Role.READER)
        self.journalist = make_user('sub_journalist', role=Role.JOURNALIST)
        self.publisher = Publisher.objects.create(name='Science Today')

    def test_reader_can_access_subscription_page(self):
        """Readers can access the subscription management page."""
        self.client.login(username='sub_reader', password='testpass123')
        response = self.client.get(reverse('subscriptions'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'news/subscriptions.html')

    def test_non_reader_redirected_from_subscriptions(self):
        """Journalists are redirected away from the subscription page."""
        self.client.login(username='sub_journalist', password='testpass123')
        response = self.client.get(reverse('subscriptions'), follow=True)
        self.assertRedirects(response, reverse('home'))

    def test_reader_can_subscribe_to_publisher(self):
        """A reader can subscribe to a publisher via the subscriptions form."""
        self.client.login(username='sub_reader', password='testpass123')
        self.client.post(reverse('subscriptions'), {
            'subscribed_publishers': [self.publisher.pk],
            'subscribed_journalists': [],
        })
        self.reader.refresh_from_db()
        self.assertIn(self.publisher, self.reader.subscribed_publishers.all())

    def test_reader_can_subscribe_to_journalist(self):
        """A reader can subscribe to a journalist via the subscriptions form."""
        self.client.login(username='sub_reader', password='testpass123')
        self.client.post(reverse('subscriptions'), {
            'subscribed_publishers': [],
            'subscribed_journalists': [self.journalist.pk],
        })
        self.reader.refresh_from_db()
        self.assertIn(self.journalist, self.reader.subscribed_journalists.all())


# ===========================================================================
# 7. REST API tests for /api/articles/
# ===========================================================================

class ArticleRestAPITest(TestCase):
    """Tests for token-auth article endpoints and role-based authorization."""

    def setUp(self):
        self.client = APIClient()

        self.reader = make_user('api_reader', role=Role.READER)
        self.journalist = make_user('api_journalist', role=Role.JOURNALIST)
        self.other_journalist = make_user('api_journalist_other', role=Role.JOURNALIST)
        self.editor = make_user('api_editor', role=Role.EDITOR)
        self.editor_group_user = make_user('api_editor_group', role=Role.READER)
        self.editor_group_user.groups.add(Group.objects.get(name='Editor'))

        self.publisher = Publisher.objects.create(name='API Publisher', description='Publisher for API tests')

        self.approved_article = make_article(
            self.journalist,
            title='Approved Article',
            approved=True,
            publisher=self.publisher,
        )
        self.unapproved_article = make_article(
            self.journalist,
            title='Draft Article',
            approved=False,
        )
        self.sports_article = make_article(
            self.journalist,
            title='Sports Headline',
            approved=True,
            section='sports',
        )

        self.reader.subscribed_journalists.add(self.journalist)
        self.reader.subscribed_publishers.add(self.publisher)

        self.reader_token = Token.objects.create(user=self.reader)
        self.journalist_token = Token.objects.create(user=self.journalist)
        self.editor_token = Token.objects.create(user=self.editor)
        self.editor_group_token = Token.objects.create(user=self.editor_group_user)

    def auth(self, token):
        """Authenticate APIClient with DRF token auth."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_api_login_success(self):
        """POST /api/login/ returns a token for valid credentials."""
        response = self.client.post(reverse('api_login'), {
            'username': 'api_reader',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_api_login_failure(self):
        """POST /api/login/ rejects invalid credentials."""
        response = self.client.post(reverse('api_login'), {
            'username': 'api_reader',
            'password': 'wrong-pass',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_articles_requires_authentication(self):
        """Unauthenticated GET /api/articles/ is denied."""
        response = self.client.get(reverse('api_articles'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_articles_returns_only_approved(self):
        """GET /api/articles/ returns approved articles only."""
        self.auth(self.reader_token)
        response = self.client.get(reverse('api_articles'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        returned_titles = [item['title'] for item in response.data]
        self.assertIn('Approved Article', returned_titles)
        self.assertNotIn('Draft Article', returned_titles)

    def test_get_articles_can_filter_by_section(self):
        """GET /api/articles/?section=sports returns only sports approved articles."""
        self.auth(self.reader_token)
        response = self.client.get(reverse('api_articles'), {'section': 'sports'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [item['title'] for item in response.data]
        self.assertIn('Sports Headline', titles)
        self.assertNotIn('Approved Article', titles)

    def test_get_subscribed_articles_can_filter_by_section(self):
        """Subscribed feed supports optional section filtering."""
        self.auth(self.reader_token)
        response = self.client.get(reverse('api_articles_subscribed'), {'section': 'sports'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item['title'] for item in response.data]
        self.assertIn('Sports Headline', titles)
        self.assertNotIn('Approved Article', titles)

    def test_reader_get_subscribed_articles_only(self):
        """Reader gets only approved content from subscribed publishers/journalists."""
        non_subscribed_article = make_article(
            self.other_journalist,
            title='Other Journalist Approved',
            approved=True,
        )

        self.auth(self.reader_token)
        response = self.client.get(reverse('api_articles_subscribed'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [item['title'] for item in response.data]
        self.assertIn('Approved Article', titles)
        self.assertNotIn(non_subscribed_article.title, titles)

    def test_non_reader_cannot_get_subscribed_articles(self):
        """Journalists cannot call reader-specific subscribed feed endpoint."""
        self.auth(self.journalist_token)
        response = self.client.get(reverse('api_articles_subscribed'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_journalist_can_create_article(self):
        """Journalist can create article via POST /api/articles/."""
        self.auth(self.journalist_token)
        payload = {
            'title': 'Created via API',
            'content': 'Body for API-created article.',
            'publisher': self.publisher.pk,
        }
        response = self.client.post(reverse('api_articles'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Created via API')

        article = Article.objects.get(title='Created via API')
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved)

    def test_reader_cannot_create_article(self):
        """Reader is forbidden from POST /api/articles/."""
        self.auth(self.reader_token)
        response = self.client.post(reverse('api_articles'), {
            'title': 'Reader Post',
            'content': 'Reader content',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_single_article_for_reader(self):
        """Reader can retrieve approved article details."""
        self.auth(self.reader_token)
        response = self.client.get(reverse('api_article_detail', args=[self.approved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.approved_article.pk)

    def test_reader_cannot_get_unapproved_article(self):
        """Reader receives 404 for unapproved article detail endpoint."""
        self.auth(self.reader_token)
        response = self.client.get(reverse('api_article_detail', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_journalist_can_update_own_article(self):
        """Journalist can update their own article."""
        self.auth(self.journalist_token)
        payload = {
            'title': 'Updated by Author',
            'content': 'Updated content',
            'publisher': self.publisher.pk,
        }
        response = self.client.put(
            reverse('api_article_detail', args=[self.unapproved_article.pk]),
            payload,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.unapproved_article.refresh_from_db()
        self.assertEqual(self.unapproved_article.title, 'Updated by Author')

    def test_journalist_cannot_update_other_article(self):
        """Journalist cannot update another journalist's article."""
        other_article = make_article(self.other_journalist, title='Other Draft', approved=False)
        self.auth(self.journalist_token)
        response = self.client.put(
            reverse('api_article_detail', args=[other_article.pk]),
            {
                'title': 'Should Fail',
                'content': 'No permission',
                'publisher': None,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_delete_article(self):
        """Editor can delete any article via API."""
        self.auth(self.editor_token)
        response = self.client.delete(reverse('api_article_detail', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Article.objects.filter(pk=self.unapproved_article.pk).exists())

    def test_reader_cannot_delete_article(self):
        """Reader cannot delete article via API."""
        self.auth(self.reader_token)
        response = self.client.delete(reverse('api_article_detail', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_approve_article(self):
        """Editor can approve article via PUT /api/articles/<id>/approve/."""
        self.auth(self.editor_token)
        response = self.client.put(reverse('api_article_approve', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.unapproved_article.refresh_from_db()
        self.assertTrue(self.unapproved_article.approved)
        self.assertEqual(self.unapproved_article.approved_by, self.editor)

    def test_journalist_cannot_approve_article(self):
        """Journalist cannot approve article via API."""
        self.auth(self.journalist_token)
        response = self.client.put(reverse('api_article_approve', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_group_user_can_approve_article(self):
        """User in Editor group can approve article via API."""
        self.auth(self.editor_group_token)
        response = self.client.put(reverse('api_article_approve', args=[self.unapproved_article.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class NewsletterSerializerBehaviorTest(TestCase):
    """Basic serializer behavior check for newsletters with approved articles."""

    def setUp(self):
        self.journalist = make_user('nl_author', role=Role.JOURNALIST)
        self.article = make_article(self.journalist, approved=True)

    def test_newsletter_contains_article_relationship(self):
        """Newsletter relationship to approved articles is persisted and serializable."""
        newsletter = Newsletter.objects.create(
            title='API Newsletter',
            description='Serializer behavior test',
            author=self.journalist,
        )
        newsletter.articles.add(self.article)

        self.assertEqual(newsletter.articles.count(), 1)
        self.assertEqual(newsletter.articles.first().title, self.article.title)


class SignalWorkflowMockTest(TestCase):
    """Ensure signal hooks call notification and API-post logic on approval transitions."""

    def setUp(self):
        self.journalist = make_user('sig_j', role=Role.JOURNALIST)
        self.article = make_article(self.journalist, approved=False)

    @patch('news.signals.post_to_approved_api')
    @patch('news.signals.notify_subscribers')
    def test_signal_triggers_on_approval_transition(self, mock_notify, mock_post):
        """Approving an existing article should trigger both side-effects once."""
        self.article.approved = True
        self.article.save()

        mock_notify.assert_called_once()
        mock_post.assert_called_once()

    @patch('news.signals.post_to_approved_api')
    @patch('news.signals.notify_subscribers')
    def test_signal_does_not_trigger_for_new_approved_create(self, mock_notify, mock_post):
        """Signal should not trigger for newly created already-approved articles."""
        make_article(self.journalist, title='Fresh Approved', approved=True)

        mock_notify.assert_not_called()
        mock_post.assert_not_called()


class AdditionalResourcesRestAPITest(TestCase):
    """Tests for /api/users, /api/newsletters, and /api/publishers endpoints."""

    def setUp(self):
        self.client = APIClient()

        self.reader = make_user('extra_reader', role=Role.READER)
        self.journalist = make_user('extra_journalist', role=Role.JOURNALIST)
        self.editor = make_user('extra_editor', role=Role.EDITOR)

        self.reader_token = Token.objects.create(user=self.reader)
        self.journalist_token = Token.objects.create(user=self.journalist)
        self.editor_token = Token.objects.create(user=self.editor)

        self.publisher = Publisher.objects.create(name='Extra Publisher', description='Extra description')
        self.article = make_article(self.journalist, title='Extra Approved', approved=True, publisher=self.publisher)

        self.newsletter = Newsletter.objects.create(
            title='Extra Newsletter',
            description='Newsletter description',
            author=self.journalist,
        )
        self.newsletter.articles.add(self.article)

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_users_endpoint_editor_only(self):
        """Only editors can list users through /api/users/."""
        unauthenticated = self.client.get(reverse('api_users'))
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        self.auth(self.reader_token)
        forbidden = self.client.get(reverse('api_users'))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.auth(self.editor_token)
        allowed = self.client.get(reverse('api_users'))
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item['username'] == 'extra_reader' for item in allowed.data))

    def test_newsletter_create_by_journalist(self):
        """Journalist can create newsletter via API and serializer writes article_ids."""
        self.auth(self.journalist_token)
        payload = {
            'title': 'Created Newsletter API',
            'description': 'Created by journalist',
            'article_ids': [self.article.pk],
        }
        response = self.client.post(reverse('api_newsletters'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Created Newsletter API')

        created = Newsletter.objects.get(title='Created Newsletter API')
        self.assertEqual(created.author, self.journalist)
        self.assertEqual(created.articles.count(), 1)

    def test_newsletter_create_forbidden_for_reader(self):
        """Reader cannot create newsletter via API."""
        self.auth(self.reader_token)
        response = self.client.post(reverse('api_newsletters'), {
            'title': 'Reader Newsletter',
            'description': 'Should fail',
            'article_ids': [self.article.pk],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_newsletter_cannot_include_unapproved_articles(self):
        """Newsletter serializer rejects unapproved article IDs."""
        draft_article = make_article(self.journalist, title='Draft in newsletter test', approved=False)

        self.auth(self.journalist_token)
        response = self.client.post(reverse('api_newsletters'), {
            'title': 'Invalid Newsletter',
            'description': 'Contains unapproved article',
            'article_ids': [draft_article.pk],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('article_ids', response.data)

    def test_newsletter_author_can_update(self):
        """Newsletter author can update newsletter details via API."""
        self.auth(self.journalist_token)
        response = self.client.put(
            reverse('api_newsletter_detail', args=[self.newsletter.pk]),
            {
                'title': 'Updated Newsletter Title',
                'description': 'Updated description',
                'article_ids': [self.article.pk],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.newsletter.refresh_from_db()
        self.assertEqual(self.newsletter.title, 'Updated Newsletter Title')

    def test_publisher_create_editor_only(self):
        """Only editors can create publishers via API."""
        unauthenticated = self.client.post(reverse('api_publishers'), {
            'name': 'No Auth Publisher',
            'description': 'Should fail unauthenticated',
        }, format='json')
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        self.auth(self.journalist_token)
        forbidden = self.client.post(reverse('api_publishers'), {
            'name': 'Journalist Publisher',
            'description': 'Should fail',
        }, format='json')
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.auth(self.editor_token)
        allowed = self.client.post(reverse('api_publishers'), {
            'name': 'Editor Publisher',
            'description': 'Created by editor',
        }, format='json')
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Publisher.objects.filter(name='Editor Publisher').exists())

    def test_authenticated_user_can_list_publishers_and_newsletters(self):
        """Authenticated users can list publisher/newsletter resources."""
        self.auth(self.reader_token)

        publishers_response = self.client.get(reverse('api_publishers'))
        self.assertEqual(publishers_response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item['name'] == 'Extra Publisher' for item in publishers_response.data))

        newsletters_response = self.client.get(reverse('api_newsletters'))
        self.assertEqual(newsletters_response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item['title'] == 'Extra Newsletter' for item in newsletters_response.data))


class PublicWeatherAPITest(TestCase):
    """Tests for public weather information endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.journalist = make_user('weather_api_j', role=Role.JOURNALIST)

        self.weather_article = make_article(
            self.journalist,
            title='Public Weather Update',
            approved=True,
            section='weather',
        )
        self.non_weather_article = make_article(
            self.journalist,
            title='Non-weather Public Update',
            approved=True,
            section='politics',
        )
        self.draft_weather_article = make_article(
            self.journalist,
            title='Draft Weather Update',
            approved=False,
            section='weather',
        )

    def test_public_weather_endpoint_allows_unauthenticated_access(self):
        """Anyone can access /api/weather/ without authentication."""
        response = self.client.get(reverse('api_weather_public'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_public_weather_endpoint_returns_only_approved_weather_articles(self):
        """Public weather feed excludes drafts and non-weather sections."""
        response = self.client.get(reverse('api_weather_public'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [item['title'] for item in response.data]
        self.assertIn('Public Weather Update', titles)
        self.assertNotIn('Non-weather Public Update', titles)
        self.assertNotIn('Draft Weather Update', titles)
