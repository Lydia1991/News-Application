"""Custom DRF permission classes for role-based API access."""
"""
permissions.py - Custom DRF permission classes for role-based API access.

Defines permission classes for Reader, Journalist, Editor, and EditorOrJournalist roles.
Used to restrict API endpoints based on user roles.
"""
from rest_framework.permissions import BasePermission

from .utils import can_act_as_editor, can_act_as_journalist, can_act_as_reader


class IsReader(BasePermission):
    """Allow access only to authenticated users with the Reader role."""

    def has_permission(self, request, view):
        return can_act_as_reader(request.user)


class IsJournalist(BasePermission):
    """Allow access only to authenticated users with the Journalist role."""

    def has_permission(self, request, view):
        return can_act_as_journalist(request.user)


class IsEditor(BasePermission):
    """Allow access only to authenticated users with the Editor role."""

    def has_permission(self, request, view):
        return can_act_as_editor(request.user)


class IsEditorOrJournalist(BasePermission):
    """Allow access to editors and journalists."""

    def has_permission(self, request, view):
        return can_act_as_editor(request.user) or can_act_as_journalist(request.user)
