from django.urls import path, include
from products.admin import admin_site
from products.views import serve_media

urlpatterns = [
    path('admin/',  admin_site.urls),
    path('',        include('products.urls')),
    path('api/',    include('products.api_urls')),
    path('api/messaging/', include('messaging.urls')),
    path('media/<path:path>', serve_media, name='serve_media'),
]
