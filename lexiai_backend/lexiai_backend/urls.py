from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from accounts.views import AdminUserDetailView, AdminUserListView

from documents.views import UserChunkDebugView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='api-schema'), name='api-redoc'),
    path('api/v1/debug/chunks/<int:user_id>/', UserChunkDebugView.as_view(), name='debug-user-chunks'),
    path('api/v1/', include('core.urls')),
    path('api/v1/auth/', include('accounts.urls')),
    # Admin-only account listing. Lives at /accounts/ (not /auth/) per the
    # admin-API spec so the URL signals "resource directory" rather than
    # "auth surface". The auth endpoints stay mounted at /auth/.
    path('api/v1/accounts/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('api/v1/accounts/users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('api/v1/documents/', include('documents.urls')),
    path('api/v1/conversations/', include('conversations.urls')),
    path('api/v1/', include('ai_engine.urls')),
]
