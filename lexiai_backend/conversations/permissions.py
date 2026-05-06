from __future__ import annotations

from rest_framework import permissions


class IsConversationOwner(permissions.BasePermission):
    message = 'You do not have access to this conversation.'

    def has_object_permission(self, request, view, obj):
        return getattr(obj, 'owner_id', None) == getattr(request.user, 'id', None)