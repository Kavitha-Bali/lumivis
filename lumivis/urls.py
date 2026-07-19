from django.urls import path, include
from products.admin import admin_site
from products.views import serve_media, serve_static

urlpatterns = [
    path('admin/',  admin_site.urls),
    path('',        include('products.urls')),
    path('api/',    include('products.api_urls')),
    path('api/messaging/', include('messaging.urls')),
    path('media/<path:path>', serve_media, name='serve_media'),
    path('static/<path:path>', serve_static, name='serve_static'),
]
