"""
forms.py - Django forms for the News Application.

Covers user registration, article creation/editing,
newsletter creation/editing, and publisher management.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Article, CustomUser, Newsletter, Publisher, Role, Tag


class RegistrationForm(UserCreationForm):
    """
    Registration form that lets a new user choose their role (Reader or
    Journalist).  Editors can only be created through the admin panel to
    prevent privilege escalation.
    """

    # Limit self-service registration to Reader and Journalist roles only
    ALLOWED_ROLES = [
        (Role.READER, 'Reader'),
        (Role.JOURNALIST, 'Journalist'),
    ]

    role = forms.ChoiceField(choices=ALLOWED_ROLES, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'role', 'password1', 'password2']

    def save(self, commit=True):
        """Save the user and assign them to the appropriate group."""
        user = super().save(commit=False)
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user


class ArticleForm(forms.ModelForm):
    """Form for journalists to create or edit an article."""

    auto_weather_update = forms.BooleanField(
        required=False,
        initial=True,
        label='Auto-generate weather summary',
        help_text='For Weather section articles, prepend a live weather summary automatically.',
    )

    class Meta:
        model = Article
        fields = ['title', 'section', 'tags', 'publisher', 'weather_location', 'story_image', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Article title'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'weather_location': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'City for weather auto-fill (e.g. Harare)'}
            ),
            'publisher': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        # Accept the current user so we can filter publishers
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Make publisher optional (independent article when left blank)
        self.fields['publisher'].required = False
        self.fields['publisher'].empty_label = '-- Independent article (no publisher) --'
        self.fields['tags'].required = False
        self.fields['tags'].queryset = Tag.objects.all()
        self.fields['auto_weather_update'].widget.attrs.update({'class': 'form-check-input'})


class NewsletterForm(forms.ModelForm):
    """Form for journalists/editors to create or edit a newsletter."""

    class Meta:
        model = Newsletter
        fields = ['title', 'description', 'articles']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Newsletter title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'articles': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only include approved articles in the selection
        self.fields['articles'].queryset = Article.objects.filter(status=Article.Status.PUBLISHED)


class PublisherForm(forms.ModelForm):
    """Form for creating or editing a Publisher (admin/editor use)."""

    class Meta:
        model = Publisher
        fields = ['name', 'description', 'editors', 'journalists']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'editors': forms.CheckboxSelectMultiple(),
            'journalists': forms.CheckboxSelectMultiple(),
        }


class SubscriptionForm(forms.ModelForm):
    """
    Form that lets a Reader manage their publisher and journalist subscriptions.
    """

    class Meta:
        model = CustomUser
        fields = ['subscribed_publishers', 'subscribed_journalists']
        widgets = {
            'subscribed_publishers': forms.CheckboxSelectMultiple(),
            'subscribed_journalists': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show journalists in the journalist subscription list
        self.fields['subscribed_journalists'].queryset = CustomUser.objects.filter(
            role=Role.JOURNALIST
        )
