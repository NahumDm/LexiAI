from __future__ import annotations

from typing import Any

from django.db import transaction

from .models import CustomUser, Profile, Role


@transaction.atomic
def create_user_with_profile(
    *,
    email: str,
    password: str,
    username: str | None = None,
    role: Role | None = None,
    profile_data: dict[str, Any] | None = None,
) -> CustomUser:
    user = CustomUser.objects.create_user(email=email, password=password, username=username, role=role)
    profile_defaults = profile_data or {}
    Profile.objects.get_or_create(user=user, defaults=profile_defaults)
    if profile_data:
        profile = user.profile
        for field_name, field_value in profile_data.items():
            setattr(profile, field_name, field_value)
        profile.save(update_fields=list(profile_data.keys()) + ['updated_at'])
    return user
