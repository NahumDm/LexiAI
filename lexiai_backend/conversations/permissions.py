from __future__ import annotations

from rest_framework import permissions


class IsConversationOwner(permissions.BasePermission):
    message = 'You do not have access to this conversation.'

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, 'owner_id', None)
        user = getattr(request, 'user', None)
        user_id = getattr(user, 'id', None)
        if owner_id is None or user_id is None or not getattr(user, 'is_authenticated', False):
            return False
        return owner_id == user_id