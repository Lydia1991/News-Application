"""
urls.py - URL routing for the 'news' application.

All URL patterns are prefixed with '' (root) because they are included
directly by the project's urls.py.
"""

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import views

urlpatterns = [
    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    path('register/', views.register_view, name='register'),
    path('login/',    views.login_view,     name='login'),
    path('logout/',   views.logout_view,    name='logout'),

    # ------------------------------------------------------------------
    # Home
    # ------------------------------------------------------------------
    path('', views.home_view, name='home'),

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------
    path('articles/create/',           views.article_create_view,  name='article_create'),
    path('articles/pending/',          views.pending_articles_view, name='pending_articles'),
    path('articles/<int:pk>/',         views.article_detail_view,  name='article_detail'),
    path('articles/<int:pk>/edit/',    views.article_edit_view,    name='article_edit'),
    path('articles/<int:pk>/delete/',  views.article_delete_view,  name='article_delete'),
    path('articles/<int:pk>/approve/', views.article_approve_view, name='article_approve'),

    # ------------------------------------------------------------------
    # Newsletters
    # ------------------------------------------------------------------
    path('newsletters/',                    views.newsletter_list_view,   name='newsletter_list'),
    path('newsletters/create/',             views.newsletter_create_view, name='newsletter_create'),
    path('newsletters/<int:pk>/',           views.newsletter_detail_view, name='newsletter_detail'),
    path('newsletters/<int:pk>/edit/',      views.newsletter_edit_view,   name='newsletter_edit'),
    path('newsletters/<int:pk>/delete/',    views.newsletter_delete_view, name='newsletter_delete'),

    # ------------------------------------------------------------------
    # Publishers
    # ------------------------------------------------------------------
    path('publishers/',          views.publisher_list_view,   name='publisher_list'),
    path('publishers/create/',   views.publisher_create_view, name='publisher_create'),
    path('publishers/<int:pk>/', views.publisher_detail_view, name='publisher_detail'),

    # ------------------------------------------------------------------
    # Subscriptions (readers)
    # ------------------------------------------------------------------
    path('subscriptions/', views.subscription_view, name='subscriptions'),

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------
    path('api/login/', obtain_auth_token, name='api_login'),
    path('api/articles/', views.ArticleListCreateAPIView.as_view(), name='api_articles'),
    path('api/weather/', views.PublicWeatherArticleListAPIView.as_view(), name='api_weather_public'),
    path('api/articles/subscribed/', views.SubscribedArticleListAPIView.as_view(), name='api_articles_subscribed'),
    path('api/articles/<int:pk>/', views.ArticleDetailAPIView.as_view(), name='api_article_detail'),
    path('api/articles/<int:pk>/approve/', views.ArticleApproveAPIView.as_view(), name='api_article_approve'),
    path('api/users/', views.UserListAPIView.as_view(), name='api_users'),
    path('api/users/<int:pk>/', views.UserDetailAPIView.as_view(), name='api_user_detail'),
    path('api/newsletters/', views.NewsletterListCreateAPIView.as_view(), name='api_newsletters'),
    path('api/newsletters/<int:pk>/', views.NewsletterDetailAPIView.as_view(), name='api_newsletter_detail'),
    path('api/publishers/', views.PublisherListCreateAPIView.as_view(), name='api_publishers'),
    path('api/publishers/<int:pk>/', views.PublisherDetailAPIView.as_view(), name='api_publisher_detail'),
    path('api/approved/', views.ApprovedArticleLogListCreateView.as_view(), name='api_approved'),
]
