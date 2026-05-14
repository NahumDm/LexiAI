from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AdminUserDetailApiTests(APITestCase):
	def setUp(self):
		self.admin = User.objects.create_user(
			email='admin-detail@example.com',
			password='password123',
			is_staff=True,
			is_superuser=True,
		)
		self.other = User.objects.create_user(email='other-detail@example.com', password='password123', is_active=True)
		self.regular = User.objects.create_user(email='regular-detail@example.com', password='password123')

	def test_admin_can_patch_is_active(self):
		self.client.force_authenticate(user=self.admin)
		response = self.client.patch(
			f'/api/v1/accounts/users/{self.other.pk}/',
			{'is_active': False},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertFalse(response.data['is_active'])
		self.other.refresh_from_db()
		self.assertFalse(self.other.is_active)

	def test_non_admin_patch_forbidden(self):
		self.client.force_authenticate(user=self.regular)
		response = self.client.patch(
			f'/api/v1/accounts/users/{self.other.pk}/',
			{'is_active': False},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_admin_cannot_deactivate_self(self):
		self.client.force_authenticate(user=self.admin)
		response = self.client.patch(
			f'/api/v1/accounts/users/{self.admin.pk}/',
			{'is_active': False},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
