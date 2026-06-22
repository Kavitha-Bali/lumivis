from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from products.admin import admin_site

urlpatterns = [
    path('admin/',  admin_site.urls),
    path('',        include('products.urls')),
    path('api/',    include('products.api_urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
