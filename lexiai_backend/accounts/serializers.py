from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Profile, Role
from .services import create_user_with_profile

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ('id', 'code', 'name')


class AccountProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='profile.full_name', allow_blank=True, required=False)
    phone_number = serializers.CharField(source='profile.phone_number', allow_blank=True, required=False)
    organization = serializers.CharField(source='profile.organization', allow_blank=True, required=False)
    bio = serializers.CharField(source='profile.bio', allow_blank=True, required=False)
    role = RoleSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'is_verified',
            'is_premium',
            'is_staff',
            'is_superuser',
            'role',
            'full_name',
            'phone_number',
            'organization',
            'bio',
            'created_at',
            'updated_at',
        )
        # `is_staff` / `is_superuser` are surfaced read-only so the SPA can gate
        # admin routes off Django's canonical admin flags (NOT a custom role
        # string). These are write-protected here — flipping them happens in
        # Django's built-in admin or via `manage.py createsuperuser`.
        read_only_fields = (
            'id', 'email', 'is_verified', 'is_premium',
            'is_staff', 'is_superuser', 'role',
            'created_at', 'updated_at',
        )

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        for attribute, value in validated_data.items():
            setattr(instance, attribute, value)
        instance.save()

        profile = getattr(instance, 'profile', None)
        if profile is None:
            profile = Profile.objects.create(user=instance)

        for attribute, value in profile_data.items():
            setattr(profile, attribute, value)
        if profile_data:
            profile.save()
        return instance

    def to_representation(self, instance):
        # Avoid 500 when legacy rows lack a Profile (RelatedObjectDoesNotExist on nested sources).
        if not Profile.objects.filter(user_id=instance.pk).exists():
            Profile.objects.get_or_create(user=instance)
        return super().to_representation(instance)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    full_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, write_only=True)
    organization = serializers.CharField(required=False, allow_blank=True, write_only=True)
    bio = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = (
            'email',
            'username',
            'password',
            'password_confirm',
            'full_name',
            'phone_number',
            'organization',
            'bio',
        )

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('password_confirm', None)
        profile_data = {
            'full_name': validated_data.pop('full_name', ''),
            'phone_number': validated_data.pop('phone_number', ''),
            'organization': validated_data.pop('organization', ''),
            'bio': validated_data.pop('bio', ''),
        }
        profile_data = {key: value for key, value in profile_data.items() if value}
        try:
            user = create_user_with_profile(
                email=validated_data['email'],
                password=password,
                username=validated_data.get('username'),
                profile_data=profile_data,
            )
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {'email': 'A user with this email or username already exists.'}
            ) from exc
        return user

    def to_representation(self, instance):
        return AccountProfileSerializer(instance, context=self.context).data


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    # CustomUser.USERNAME_FIELD is ``email``; accept ``email`` in JSON (not ``username``).
    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = AccountProfileSerializer(self.user, context=self.context).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role.code if user.role else None
        token['is_verified'] = user.is_verified
        token['is_premium'] = user.is_premium
        return token


class AdminUserSerializer(serializers.ModelSerializer):
    """
    Read-only admin view of every account on the system.

    Exposes the minimal set the admin SPA needs to render its user table:
    identity (id/email/username), display name parts, and the canonical
    Django auth flags (`is_staff`, `is_superuser`, `is_active`). `last_login`
    is mirrored from `AbstractBaseUser` for "last active" UI; `date_joined`
    mirrors what `auth.User` exposes and is what `/accounts/users/` consumers
    expect per the admin-API spec.
    """

    role = RoleSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'role',
            'is_active',
            'is_staff',
            'is_superuser',
            'is_verified',
            'is_premium',
            'date_joined',
            'last_login',
            'created_at',
        )
        read_only_fields = fields


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Writable subset for PATCH /api/v1/accounts/users/<id>/ (IsAdminUser only).
    Response shape is normalized via ``AdminUserSerializer`` in ``to_representation``.
    """

    class Meta:
        model = User
        fields = ('is_active', 'is_staff', 'is_superuser')

    def validate(self, attrs):
        request = self.context.get('request')
        instance = self.instance
        if request is None or not getattr(request.user, 'is_authenticated', False) or instance is None:
            return attrs

        if instance.pk == request.user.pk:
            if attrs.get('is_active') is False:
                raise serializers.ValidationError(
                    {'is_active': 'You cannot deactivate your own account via the API.'}
                )
            if 'is_staff' in attrs and attrs['is_staff'] != instance.is_staff:
                raise serializers.ValidationError(
                    {'is_staff': 'You cannot change your own staff flag via the API.'}
                )
            if 'is_superuser' in attrs and attrs['is_superuser'] != instance.is_superuser:
                raise serializers.ValidationError(
                    {'is_superuser': 'You cannot change your own superuser flag via the API.'}
                )

        if 'is_superuser' in attrs and not request.user.is_superuser:
            raise serializers.ValidationError(
                {'is_superuser': 'Only superusers may change superuser privileges.'}
            )

        return attrs

    def update(self, instance, validated_data):
        if validated_data.get('is_superuser') is True:
            validated_data['is_staff'] = True
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        return AdminUserSerializer(instance, context=self.context).data
