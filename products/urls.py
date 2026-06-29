from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('products/', views.products_page, name='products'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/buy/<int:pk>/',    views.buy_now,          name='buy_now'),
    path('cart/remove/<int:pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:pk>/', views.update_cart, name='update_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('order-success/', views.order_success, name='order_success'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),

    # Wishlist
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/toggle/<int:pk>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('wishlist/checkout/', views.wishlist_checkout, name='wishlist_checkout'),

    # Panels
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('my-account/', views.user_panel, name='user_panel'),

    # Order cancellation
    path('order/cancel/<str:order_id>/', views.cancel_order, name='cancel_order'),
    path('admin-panel/cancel/<int:pk>/<str:action>/', views.admin_cancel_review, name='admin_cancel_review'),

    # Live search
    path('search/suggest/', views.search_suggestions, name='search_suggest'),
]
