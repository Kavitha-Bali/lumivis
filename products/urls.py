from django.contrib import admin
from django.urls import path
from .views import products

urlpatterns = [
    path('admin/', admin.site.urls),
    path('products/', products, name='products')
    path('promocode/',promocode,name='promocode'),
    path('transactions/', transactions, name='transactions'),

    
]
     


