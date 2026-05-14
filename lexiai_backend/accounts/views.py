from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from .models import Profile
from .serializers import (
    AccountProfileSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
	serializer_class = RegisterSerializer
	permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
	serializer_class = EmailTokenObtainPairSerializer
	permission_classes = [permissions.AllowAny]


class RefreshView(TokenRefreshView):
	permission_classes = [permissions.AllowAny]


class LogoutView(TokenBlacklistView):
	"""
	Blacklist the supplied refresh token.

	`simple_jwt.views.TokenBlacklistView` ships with
	``authentication_classes = ()`` and ``permission_classes = ()`` — possession
	of a valid refresh token is the only thing required to invalidate it. We
	intentionally keep AllowAny here: layering ``IsAuthenticated`` on top
	WITHOUT also setting ``authentication_classes`` (as the old code did) means
	DRF treats every caller as ``AnonymousUser`` and returns 403 even with a
	valid bearer token, silently breaking logout.
	"""

	authentication_classes = [JWTAuthentication]
	permission_classes = [permissions.AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
	serializer_class = AccountProfileSerializer
	permission_classes = [permissions.IsAuthenticated]

	def get_object(self):
		return self.request.user


class AdminUserListView(generics.ListAPIView):
	"""
	GET /api/v1/accounts/users/
	
	Admin-only list of every account on the system. Optional `?search=`
	filters across email, username, first/last name (case-insensitive
	substring match).

	Pagination is intentionally disabled here. The response is an envelope::

	    { "count": <matches for ?search=>, "results": [...], "stats": { "total", "active", "staff" } }

	`stats` are GLOBAL (full user table) so stat cards stay correct while the
	table reflects the optional `?search=` filter.
	"""
	serializer_class = AdminUserSerializer
	permission_classes = [permissions.IsAdminUser]
	pagination_class = None

	def get_queryset(self):
		queryset = User.objects.select_related('role', 'profile').order_by('-date_joined')
		search = self.request.query_params.get('search')
		if search:
			# `icontains` is intentional — admins type partial strings into the
			# filter box. We OR across the human-readable fields. `username`
			# can be NULL (see CustomUser); `Q` handles that without us
			# needing explicit `__isnull` guards because the join is implicit.
			queryset = queryset.filter(
				Q(email__icontains=search)
				| Q(username__icontains=search)
				| Q(first_name__icontains=search)
				| Q(last_name__icontains=search)
			)
		return queryset

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		all_users = User.objects.all()
		stats = {
			'total': all_users.count(),
			'active': all_users.filter(is_active=True).count(),
			'staff': all_users.filter(Q(is_staff=True) | Q(is_superuser=True)).count(),
		}
		return Response(
			{
				'count': queryset.count(),
				'results': serializer.data,
				'stats': stats,
			}
		)


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
	"""
	GET /api/v1/accounts/users/<id>/ — read single account (admin).
	PATCH /api/v1/accounts/users/<id>/ — partial update of is_active, is_staff, is_superuser.
	"""

	queryset = User.objects.select_related('role', 'profile').all()
	permission_classes = [permissions.IsAdminUser]
	http_method_names = ['get', 'patch', 'head', 'options']

	def get_serializer_class(self):
		if self.request.method == 'PATCH':
			return AdminUserUpdateSerializer
		return AdminUserSerializer


class GuestSessionView(APIView):
	"""
	Create an ephemeral authenticated guest user and return JWT pair (same shape as login).
	Frontend enforces guest query limits in sessionStorage.
	"""

	permission_classes = [permissions.AllowAny]

	def post(self, request):
		uid = uuid.uuid4().hex[:16]
		email = f'guest_{uid}@guest.lexiai.local'
		username = f'guest_{uid}'
		user = User.objects.create_user(
			email=email,
			username=username,
			first_name='Guest',
			last_name='User',
		)
		Profile.objects.get_or_create(user=user, defaults={'full_name': 'Guest User'})
		refresh = RefreshToken.for_user(user)
		payload = {
			'access': str(refresh.access_token),
			'refresh': str(refresh),
			'user': AccountProfileSerializer(user).data,
		}
		return Response(payload, status=status.HTTP_200_OK)
