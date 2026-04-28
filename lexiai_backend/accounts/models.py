from __future__ import annotations

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.Model):
	code = models.SlugField(max_length=50, unique=True)
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	is_system_role = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['name']

	def __str__(self) -> str:
		return self.name


class CustomUserManager(BaseUserManager):
	use_in_migrations = True

	def create_user(self, email: str, password: str | None = None, **extra_fields):
		if not email:
			raise ValueError('The email address must be set.')

		email = self.normalize_email(email).lower()
		user = self.model(email=email, **extra_fields)
		if password:
			user.set_password(password)
		else:
			user.set_unusable_password()
		user.full_clean(exclude=['password'])
		user.save(using=self._db)
		return user

	def create_superuser(self, email: str, password: str | None = None, **extra_fields):
		extra_fields.setdefault('is_staff', True)
		extra_fields.setdefault('is_superuser', True)
		extra_fields.setdefault('is_active', True)

		if extra_fields.get('is_staff') is not True:
			raise ValueError('Superuser must have is_staff=True.')
		if extra_fields.get('is_superuser') is not True:
			raise ValueError('Superuser must have is_superuser=True.')

		return self.create_user(email=email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
	email = models.EmailField(unique=True)
	username = models.CharField(max_length=150, unique=True, null=True, blank=True)
	first_name = models.CharField(max_length=150, blank=True)
	last_name = models.CharField(max_length=150, blank=True)
	role = models.ForeignKey(
		Role,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='users',
	)
	is_verified = models.BooleanField(default=False)
	is_premium = models.BooleanField(default=False)
	is_staff = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	date_joined = models.DateTimeField(default=timezone.now)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	objects = CustomUserManager()

	USERNAME_FIELD = 'email'
	REQUIRED_FIELDS: list[str] = []

	class Meta:
		ordering = ['email']

	def __str__(self) -> str:
		return self.email

	def clean(self):
		super().clean()
		self.email = self.__class__.objects.normalize_email(self.email).lower()
		if self.username == '':
			self.username = None

	def save(self, *args, **kwargs):
		self.full_clean(exclude=['password'])
		return super().save(*args, **kwargs)

	def get_full_name(self) -> str:
		full_name = f'{self.first_name} {self.last_name}'.strip()
		return full_name or self.username or self.email

	def get_short_name(self) -> str:
		return self.first_name or self.username or self.email


class Profile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
	full_name = models.CharField(max_length=255, blank=True)
	phone_number = models.CharField(max_length=32, blank=True)
	organization = models.CharField(max_length=255, blank=True)
	bio = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['user__email']

	def __str__(self) -> str:
		return f'Profile<{self.user.email}>'
