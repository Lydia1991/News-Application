"""
views.py - View functions for the News Application.

Organised into sections:
  1. Authentication (login, logout, register)
  2. Home / article listing
  3. Article CRUD + approval
  4. Newsletter CRUD
  5. Publisher management
  6. Subscription management
  7. REST API views (ApprovedArticleLog)
"""

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Q

from rest_framework import permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import (
    ArticleForm,
    NewsletterForm,
    PublisherForm,
    RegistrationForm,
    SubscriptionForm,
)
from .models import (
    ApprovedArticleLog,
    Article,
    CustomUser,
    Newsletter,
    Publisher,
)
from .permissions import IsEditor, IsReader
from .serializers import (
    ApprovedArticleLogSerializer,
    ArticleSerializer,
    NewsletterSerializer,
    PublisherSerializer,
    UserSerializer,
)
from .utils import assign_role_group
from .utils import can_act_as_editor, can_act_as_journalist, can_act_as_reader
from .utils import generate_weather_story


# ===========================================================================
# 1. Authentication
# ===========================================================================

def register_view(request):
    """Handle new-user registration and role assignment."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Assign the user to the correct Django group based on their role
            assign_role_group(user)
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('home')
    else:
        form = RegistrationForm()

    return render(request, 'news/register.html', {'form': form})


def login_view(request):
    """Authenticate and log in a user."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = (
            request.POST.get('news_username')
            or request.POST.get('username')
            or ''
        ).strip()
        password = (
            request.POST.get('news_password')
            or request.POST.get('password')
            or ''
        )
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Redirect to 'next' param if provided, otherwise home
            next_url = request.POST.get('next') or request.GET.get('next') or 'home'
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'news/login.html')


@login_required
def logout_view(request):
    """Log out the current user."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


# ===========================================================================
# 2. Home / article listing
# ===========================================================================

def home_view(request):
    """
    Home page.

    - Unauthenticated / reader: shows all approved articles.
    - Journalist: shows their own articles (any status) + all approved.
    - Editor: shows all articles (approved and pending).
    """
    user = request.user
    selected_section = request.GET.get('section', 'all')
    selected_status = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    weather_location_query = request.GET.get('weather_location', '').strip()
    live_weather_summary = None
    show_status_filters = user.is_authenticated and not can_act_as_reader(user)

    if not user.is_authenticated or can_act_as_reader(user):
        articles = Article.objects.filter(status=Article.Status.PUBLISHED).select_related('author', 'publisher')
    elif can_act_as_journalist(user):
        # Journalist sees their own articles (any status) plus all published
        articles = Article.objects.filter(
            Q(status=Article.Status.PUBLISHED) | Q(author=user)
        ).select_related('author', 'publisher').order_by('-created_at')
    else:
        # Editor sees everything
        articles = Article.objects.all().select_related('author', 'publisher')

    valid_sections = {choice[0] for choice in Article.Section.choices}
    valid_statuses = {choice[0] for choice in Article.Status.choices}
    if selected_section in valid_sections:
        articles = articles.filter(section=selected_section)
    else:
        selected_section = 'all'

    if show_status_filters and selected_status in valid_statuses:
        articles = articles.filter(status=selected_status)
    else:
        selected_status = 'all'

    if search_query:
        articles = articles.filter(
            Q(title__icontains=search_query)
            | Q(content__icontains=search_query)
            | Q(author__username__icontains=search_query)
            | Q(publisher__name__icontains=search_query)
        ).distinct()

    # Optional on-demand weather snapshot for the Weather section.
    if selected_section == Article.Section.WEATHER and request.GET.get('live_weather') == '1':
        location = weather_location_query or 'Harare'
        weather_location_query = location
        live_weather_summary = generate_weather_story(location=location)

    # Keep the feed fast and readable with page-based navigation.
    paginator = Paginator(articles, 6)
    page_obj = paginator.get_page(request.GET.get('page'))

    pending_in_selected_section = 0
    if selected_section in valid_sections:
        pending_in_selected_section = Article.objects.filter(
            section=selected_section,
            status=Article.Status.PENDING_REVIEW,
        ).count()

    newsletters = Newsletter.objects.all().select_related('author')[:5]
    publishers = Publisher.objects.all()[:5]

    context = {
        'articles': articles,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'newsletters': newsletters,
        'publishers': publishers,
        'selected_section': selected_section,
        'selected_status': selected_status,
        'show_status_filters': show_status_filters,
        'search_query': search_query,
        'weather_location_query': weather_location_query,
        'live_weather_summary': live_weather_summary,
        'section_choices': Article.Section.choices,
        'status_choices': Article.Status.choices,
        'pending_in_selected_section': pending_in_selected_section,
    }

    context['articles'] = page_obj.object_list

    if user.is_authenticated and can_act_as_editor(user):
        context['pending_count'] = Article.objects.filter(status=Article.Status.PENDING_REVIEW).count()
        context['approved_count'] = Article.objects.filter(status=Article.Status.PUBLISHED).count()
        context['total_articles'] = Article.objects.count()
        context['publisher_count'] = Publisher.objects.count()

    return render(request, 'news/home.html', context)


# ===========================================================================
# 3. Article CRUD + approval
# ===========================================================================

def article_detail_view(request, pk):
    """Show a single article.  Non-approved articles are hidden from readers."""
    article = get_object_or_404(Article, pk=pk)
    user = request.user

    # Readers and anonymous users may only see approved articles
    if article.status != Article.Status.PUBLISHED:
        if not user.is_authenticated or can_act_as_reader(user):
            messages.error(request, 'This article has not been approved yet.')
            return redirect('home')

    related = Article.objects.filter(status=Article.Status.PUBLISHED).exclude(pk=article.pk)
    if article.tags.exists():
        related = related.filter(tags__in=article.tags.all())
    else:
        related = related.filter(section=article.section)

    related_articles = related.select_related('author', 'publisher').distinct()[:4]

    return render(
        request,
        'news/article_detail.html',
        {
            'article': article,
            'related_articles': related_articles,
        },
    )


@login_required
def article_create_view(request):
    """Allow journalists to submit a new article for editorial review."""
    if not can_act_as_journalist(request.user):
        messages.error(request, 'Only journalists can create articles.')
        return redirect('home')

    if request.method == 'POST':
        form = ArticleForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            save_as_draft = 'save_draft' in request.POST
            article.status = Article.Status.DRAFT if save_as_draft else Article.Status.PENDING_REVIEW
            article.approved_by = None
            article.approved_at = None
            auto_weather_update = form.cleaned_data.get('auto_weather_update', True)

            if article.section == Article.Section.WEATHER and auto_weather_update:
                location = (article.weather_location or '').strip() or 'Harare'
                article.weather_location = location
                auto_story = generate_weather_story(location=location)
                if auto_story:
                    manual_content = (article.content or '').strip()
                    article.content = f'{auto_story}\n\n{manual_content}' if manual_content else auto_story

            article.save()
            form.save_m2m()
            if save_as_draft:
                messages.success(request, 'Draft saved. You can submit it for review later.')
            else:
                messages.success(request, 'Article submitted for editorial review.')
            return redirect('article_detail', pk=article.pk)
    else:
        form = ArticleForm(user=request.user)

    return render(request, 'news/article_form.html', {'form': form, 'action': 'Create'})


@login_required
def article_edit_view(request, pk):
    """Allow the original journalist or an editor to edit an article."""
    article = get_object_or_404(Article, pk=pk)
    user = request.user

    # Access control: only the author or an editor may edit
    if not (can_act_as_editor(user) or article.author == user):
        messages.error(request, 'You do not have permission to edit this article.')
        return redirect('article_detail', pk=pk)

    if request.method == 'POST':
        form = ArticleForm(request.POST, request.FILES, instance=article, user=user)
        if form.is_valid():
            updated_article = form.save(commit=False)
            save_as_draft = 'save_draft' in request.POST
            if not can_act_as_editor(user):
                updated_article.status = (
                    Article.Status.DRAFT if save_as_draft else Article.Status.PENDING_REVIEW
                )
                updated_article.approved_by = None
                updated_article.approved_at = None

            auto_weather_update = form.cleaned_data.get('auto_weather_update', True)

            if updated_article.section == Article.Section.WEATHER and auto_weather_update:
                location = (updated_article.weather_location or '').strip() or 'Harare'
                updated_article.weather_location = location
                auto_story = generate_weather_story(location=location)
                if auto_story:
                    content = (updated_article.content or '').strip()
                    marker = '\n\n'
                    if marker in content:
                        _, tail = content.split(marker, 1)
                        updated_article.content = f'{auto_story}{marker}{tail.strip()}'
                    else:
                        updated_article.content = f'{auto_story}{marker}{content}' if content else auto_story

            updated_article.save()
            form.save_m2m()
            if not can_act_as_editor(user) and save_as_draft:
                messages.success(request, 'Draft updated successfully.')
            elif not can_act_as_editor(user):
                messages.success(request, 'Article updated and sent for editorial review.')
            else:
                messages.success(request, 'Article updated successfully.')
            return redirect('article_detail', pk=article.pk)
    else:
        form = ArticleForm(instance=article, user=user)

    return render(request, 'news/article_form.html', {'form': form, 'action': 'Edit', 'article': article})


@login_required
def article_delete_view(request, pk):
    """Allow the article author or an editor to delete an article."""
    article = get_object_or_404(Article, pk=pk)
    user = request.user

    if not (can_act_as_editor(user) or article.author == user):
        messages.error(request, 'You do not have permission to delete this article.')
        return redirect('article_detail', pk=pk)

    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Article deleted.')
        return redirect('home')

    return render(request, 'news/article_confirm_delete.html', {'article': article})


@login_required
def article_approve_view(request, pk):
    """
    Allow an editor (by role or group) to approve a submitted article.

    Access control:
      - Only users with role='editor' OR belonging to the 'Editor' group
        may access this view.  All others are redirected with an error.

    On POST (confirmation submitted):
      1. Marks the article approved and records the approving editor + timestamp.
      2. Explicitly emails all subscribers of the journalist and/or publisher
         (handled directly here, not relying solely on signals).
      3. Explicitly POSTs the approval event to the internal /api/approved/
         REST endpoint to log it (handled directly here as well).

    Signal note: the post_save signal (signals.py) also fires and performs
    the same two side-effects, but having the logic here ensures correctness
    even if signal dispatch is bypassed (e.g. update_fields or bulk ops).
    """
    # ── Access control ────────────────────────────────────────────────────
    if not can_act_as_editor(request.user):
        messages.error(request, 'Only editors can approve articles.')
        return redirect('article_detail', pk=pk)

    article = get_object_or_404(Article, pk=pk)

    if article.status == Article.Status.PUBLISHED:
        messages.info(request, 'This article has already been approved.')
        return redirect('article_detail', pk=pk)

    if request.method == 'POST':
        # ── Step 1: Mark as approved ──────────────────────────────────────
        article.status = Article.Status.PUBLISHED
        article.approved_by = request.user
        article.approved_at = timezone.now()
        article.editor_feedback = (request.POST.get('editor_feedback') or '').strip()
        # Save with update_fields so we don't re-trigger unrelated side-effects.
        # _previously_approved is set to False by the model's save() override,
        # so the signal will also fire correctly on a full save below.
        article.save()

        # ── Step 2: Email subscribers (inline — direct view responsibility) ─
        from .utils import notify_subscribers
        notify_subscribers(article)

        # ── Step 3: POST to /api/approved/ (inline — direct view responsibility)
        from .utils import post_to_approved_api
        post_to_approved_api(article, request=request)

        messages.success(
            request,
            f'Article "{article.title}" approved. Subscribers notified and event logged.'
        )
        return redirect('article_detail', pk=pk)

    return render(request, 'news/article_approve.html', {'article': article})


@login_required
def pending_articles_view(request):
    """List all articles pending editorial review (editors only)."""
    if not can_act_as_editor(request.user):
        messages.error(request, 'Only editors can view the pending articles queue.')
        return redirect('home')

    selected_status = request.GET.get('status', Article.Status.PENDING_REVIEW)
    valid_statuses = {choice[0] for choice in Article.Status.choices}

    pending = Article.objects.select_related('author', 'publisher')
    if selected_status in valid_statuses:
        pending = pending.filter(status=selected_status)
    else:
        selected_status = 'all'

    context = {
        'pending': pending,
        'selected_status': selected_status,
        'status_choices': Article.Status.choices,
    }
    return render(request, 'news/pending_articles.html', context)


# ===========================================================================
# 4. Newsletter CRUD
# ===========================================================================

def newsletter_list_view(request):
    """Display all newsletters."""
    newsletters = Newsletter.objects.all().select_related('author')
    return render(request, 'news/newsletter_list.html', {'newsletters': newsletters})


def newsletter_detail_view(request, pk):
    """Display a single newsletter and its articles."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    return render(request, 'news/newsletter_detail.html', {'newsletter': newsletter})


@login_required
def newsletter_create_view(request):
    """Allow journalists and editors to create a newsletter."""
    if can_act_as_reader(request.user):
        messages.error(request, 'Readers cannot create newsletters.')
        return redirect('newsletter_list')

    if request.method == 'POST':
        form = NewsletterForm(request.POST)
        if form.is_valid():
            newsletter = form.save(commit=False)
            newsletter.author = request.user
            newsletter.save()
            form.save_m2m()  # Save the many-to-many articles relation
            messages.success(request, 'Newsletter created successfully.')
            return redirect('newsletter_detail', pk=newsletter.pk)
    else:
        form = NewsletterForm()

    return render(request, 'news/newsletter_form.html', {'form': form, 'action': 'Create'})


@login_required
def newsletter_edit_view(request, pk):
    """Allow the newsletter author or an editor to edit a newsletter."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    user = request.user

    if not (can_act_as_editor(user) or newsletter.author == user):
        messages.error(request, 'You do not have permission to edit this newsletter.')
        return redirect('newsletter_detail', pk=pk)

    if request.method == 'POST':
        form = NewsletterForm(request.POST, instance=newsletter)
        if form.is_valid():
            form.save()
            messages.success(request, 'Newsletter updated.')
            return redirect('newsletter_detail', pk=newsletter.pk)
    else:
        form = NewsletterForm(instance=newsletter)

    return render(request, 'news/newsletter_form.html', {'form': form, 'action': 'Edit', 'newsletter': newsletter})


@login_required
def newsletter_delete_view(request, pk):
    """Allow the newsletter author or an editor to delete a newsletter."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    user = request.user

    if not (can_act_as_editor(user) or newsletter.author == user):
        messages.error(request, 'You do not have permission to delete this newsletter.')
        return redirect('newsletter_detail', pk=pk)

    if request.method == 'POST':
        newsletter.delete()
        messages.success(request, 'Newsletter deleted.')
        return redirect('newsletter_list')

    return render(request, 'news/newsletter_confirm_delete.html', {'newsletter': newsletter})


# ===========================================================================
# 5. Publisher management (editor-only)
# ===========================================================================

def publisher_list_view(request):
    """List all publishers."""
    publishers = Publisher.objects.all()
    return render(request, 'news/publisher_list.html', {'publishers': publishers})


def publisher_detail_view(request, pk):
    """Show details for a single publisher."""
    publisher = get_object_or_404(Publisher, pk=pk)
    articles = Article.objects.filter(publisher=publisher, status=Article.Status.PUBLISHED)
    return render(request, 'news/publisher_detail.html', {
        'publisher': publisher,
        'articles': articles,
    })


@login_required
def publisher_create_view(request):
    """Allow editors to create a publisher."""
    if not can_act_as_editor(request.user):
        messages.error(request, 'Only editors can manage publishers.')
        return redirect('publisher_list')

    if request.method == 'POST':
        form = PublisherForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Publisher created.')
            return redirect('publisher_list')
    else:
        form = PublisherForm()

    return render(request, 'news/publisher_form.html', {'form': form, 'action': 'Create'})


# ===========================================================================
# 6. Subscription management (reader-only)
# ===========================================================================

@login_required
def subscription_view(request):
    """Allow readers to manage their publisher and journalist subscriptions."""
    if not can_act_as_reader(request.user):
        messages.error(request, 'Only readers can manage subscriptions.')
        return redirect('home')

    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Subscriptions updated.')
            return redirect('home')
    else:
        form = SubscriptionForm(instance=request.user)

    return render(request, 'news/subscriptions.html', {'form': form})


# ===========================================================================
# 7. REST API views
# ===========================================================================

class ApprovedArticleLogListCreateView(APIView):
    """
    GET  /api/approved/  – list all approval log entries.
    POST /api/approved/  – log a newly approved article.

    This endpoint is called internally by the post_save signal whenever
    an editor approves an article, simulating a third-party integration.
    """

    # Allow internal signal integration to POST without auth token.
    def get_permissions(self):
        return [permissions.AllowAny()]

    def get(self, request):
        """Return a list of all approval log entries."""
        logs = ApprovedArticleLog.objects.select_related('article').all()
        serializer = ApprovedArticleLogSerializer(logs, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Persist a new approval event sent by the internal signal."""
        serializer = ApprovedArticleLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ArticleListCreateAPIView(APIView):
    """
    GET /api/articles/          -> list approved articles for authenticated users.
    POST /api/articles/         -> create article (journalists only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        articles = Article.objects.filter(status=Article.Status.PUBLISHED).select_related('author', 'publisher')
        section = request.query_params.get('section')
        if section in {choice[0] for choice in Article.Section.choices}:
            articles = articles.filter(section=section)
        serializer = ArticleSerializer(articles, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_act_as_journalist(request.user):
            return Response(
                {'detail': 'Only journalists can create articles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ArticleSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            article = serializer.save()
            response_serializer = ArticleSerializer(article)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscribedArticleListAPIView(APIView):
    """
    GET /api/articles/subscribed/ -> approved articles from reader subscriptions.
    """

    permission_classes = [IsAuthenticated, IsReader]

    def get(self, request):
        reader = request.user

        queryset = Article.objects.filter(
            status=Article.Status.PUBLISHED
        ).filter(
            Q(author__in=reader.subscribed_journalists.all())
            | Q(publisher__in=reader.subscribed_publishers.all())
        ).select_related('author', 'publisher').distinct()

        section = request.query_params.get('section')
        if section in {choice[0] for choice in Article.Section.choices}:
            queryset = queryset.filter(section=section)

        serializer = ArticleSerializer(queryset, many=True)
        return Response(serializer.data)


class PublicWeatherArticleListAPIView(APIView):
    """
    GET /api/weather/ -> publicly accessible list of approved weather articles.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = Article.objects.filter(
            status=Article.Status.PUBLISHED,
            section=Article.Section.WEATHER,
        ).select_related('author', 'publisher').order_by('-created_at')

        serializer = ArticleSerializer(queryset, many=True)
        return Response(serializer.data)


class ArticleDetailAPIView(APIView):
    """
    GET    /api/articles/<id>/ -> retrieve a single article.
    PUT    /api/articles/<id>/ -> update article (editors/journalists).
    DELETE /api/articles/<id>/ -> delete article (editors/journalists).
    """

    permission_classes = [IsAuthenticated]

    def _get_article(self, pk):
        return get_object_or_404(Article.objects.select_related('author', 'publisher'), pk=pk)

    def get(self, request, pk):
        article = self._get_article(pk)

        if can_act_as_reader(request.user) and article.status != Article.Status.PUBLISHED:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if (
            can_act_as_journalist(request.user)
            and article.status != Article.Status.PUBLISHED
            and article.author != request.user
        ):
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ArticleSerializer(article)
        return Response(serializer.data)

    def put(self, request, pk):
        article = self._get_article(pk)

        if not (can_act_as_editor(request.user) or can_act_as_journalist(request.user)):
            return Response(
                {'detail': 'Only editors and journalists can update articles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if can_act_as_journalist(request.user) and not can_act_as_editor(request.user) and article.author != request.user:
            return Response(
                {'detail': 'Journalists can only update their own articles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ArticleSerializer(article, data=request.data, partial=False)
        if serializer.is_valid():
            updated_article = serializer.save()
            # Journalist edits are resubmitted for approval.
            if can_act_as_journalist(request.user) and not can_act_as_editor(request.user):
                updated_article.status = Article.Status.PENDING_REVIEW
                updated_article.approved_by = None
                updated_article.approved_at = None
                updated_article.save()
            return Response(ArticleSerializer(updated_article).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        article = self._get_article(pk)

        if not (can_act_as_editor(request.user) or can_act_as_journalist(request.user)):
            return Response(
                {'detail': 'Only editors and journalists can delete articles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if can_act_as_journalist(request.user) and not can_act_as_editor(request.user) and article.author != request.user:
            return Response(
                {'detail': 'Journalists can only delete their own articles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        article.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticleApproveAPIView(APIView):
    """PUT /api/articles/<id>/approve/ -> approve article (editors only)."""

    permission_classes = [IsAuthenticated, IsEditor]

    def put(self, request, pk):
        article = get_object_or_404(Article, pk=pk)

        if article.status == Article.Status.PUBLISHED:
            return Response({'detail': 'Article is already approved.'}, status=status.HTTP_200_OK)

        article.status = Article.Status.PUBLISHED
        article.approved_by = request.user
        article.approved_at = timezone.now()
        article.editor_feedback = (request.data.get('editor_feedback') or '').strip()
        article.save()

        return Response(ArticleSerializer(article).data, status=status.HTTP_200_OK)


class UserListAPIView(APIView):
    """
    GET /api/users/ -> list all users (editors only).
    """

    permission_classes = [IsAuthenticated, IsEditor]

    def get(self, request):
        queryset = CustomUser.objects.all().order_by('username')
        role = request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)


class UserDetailAPIView(APIView):
    """
    GET /api/users/<id>/ -> retrieve a single user (editors only).
    """

    permission_classes = [IsAuthenticated, IsEditor]

    def get(self, request, pk):
        user_obj = get_object_or_404(CustomUser, pk=pk)
        return Response(UserSerializer(user_obj).data)


class NewsletterListCreateAPIView(APIView):
    """
    GET  /api/newsletters/ -> list newsletters (authenticated users).
    POST /api/newsletters/ -> create newsletter (editors/journalists only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Newsletter.objects.select_related('author').prefetch_related('articles').all()
        serializer = NewsletterSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not (can_act_as_editor(request.user) or can_act_as_journalist(request.user)):
            return Response(
                {'detail': 'Only editors and journalists can create newsletters.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = NewsletterSerializer(data=request.data)
        if serializer.is_valid():
            newsletter = serializer.save(author=request.user)
            return Response(NewsletterSerializer(newsletter).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NewsletterDetailAPIView(APIView):
    """
    GET    /api/newsletters/<id>/ -> retrieve newsletter.
    PUT    /api/newsletters/<id>/ -> update newsletter (author/editor).
    DELETE /api/newsletters/<id>/ -> delete newsletter (author/editor).
    """

    permission_classes = [IsAuthenticated]

    def _get_newsletter(self, pk):
        return get_object_or_404(
            Newsletter.objects.select_related('author').prefetch_related('articles'),
            pk=pk,
        )

    def get(self, request, pk):
        newsletter = self._get_newsletter(pk)
        return Response(NewsletterSerializer(newsletter).data)

    def put(self, request, pk):
        newsletter = self._get_newsletter(pk)

        if not (can_act_as_editor(request.user) or newsletter.author == request.user):
            return Response(
                {'detail': 'Only editors or the newsletter author can update this newsletter.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = NewsletterSerializer(newsletter, data=request.data, partial=False)
        if serializer.is_valid():
            updated = serializer.save()
            return Response(NewsletterSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        newsletter = self._get_newsletter(pk)

        if not (can_act_as_editor(request.user) or newsletter.author == request.user):
            return Response(
                {'detail': 'Only editors or the newsletter author can delete this newsletter.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        newsletter.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublisherListCreateAPIView(APIView):
    """
    GET  /api/publishers/ -> list publishers (authenticated users).
    POST /api/publishers/ -> create publisher (editors only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Publisher.objects.all().order_by('name')
        serializer = PublisherSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_act_as_editor(request.user):
            return Response(
                {'detail': 'Only editors can create publishers.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PublisherSerializer(data=request.data)
        if serializer.is_valid():
            publisher = serializer.save()
            return Response(PublisherSerializer(publisher).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PublisherDetailAPIView(APIView):
    """
    GET    /api/publishers/<id>/ -> retrieve publisher.
    PUT    /api/publishers/<id>/ -> update publisher (editors only).
    DELETE /api/publishers/<id>/ -> delete publisher (editors only).
    """

    permission_classes = [IsAuthenticated]

    def _get_publisher(self, pk):
        return get_object_or_404(Publisher, pk=pk)

    def get(self, request, pk):
        publisher = self._get_publisher(pk)
        return Response(PublisherSerializer(publisher).data)

    def put(self, request, pk):
        if not can_act_as_editor(request.user):
            return Response(
                {'detail': 'Only editors can update publishers.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        publisher = self._get_publisher(pk)
        serializer = PublisherSerializer(publisher, data=request.data, partial=False)
        if serializer.is_valid():
            updated = serializer.save()
            return Response(PublisherSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not can_act_as_editor(request.user):
            return Response(
                {'detail': 'Only editors can delete publishers.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        publisher = self._get_publisher(pk)
        publisher.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
