from __future__ import annotations

from django.contrib.auth import get_user_model
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
            'role',
            'full_name',
            'phone_number',
            'organization',
            'bio',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'email', 'is_verified', 'is_premium', 'role', 'created_at', 'updated_at')

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
        user = create_user_with_profile(
            email=validated_data['email'],
            password=password,
            username=validated_data.get('username'),
            profile_data=profile_data,
        )
        return user

    def to_representation(self, instance):
        return AccountProfileSerializer(instance, context=self.context).data


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
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
