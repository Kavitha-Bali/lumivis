from django.urls import path
from . import api_views

urlpatterns = [

    # ── Auth ────────────────────────────────────────────────────────────────
    path('auth/register/',         api_views.RegisterAPIView.as_view(),       name='api_register'),
    path('auth/login/',            api_views.LoginAPIView.as_view(),          name='api_login'),
    path('auth/logout/',           api_views.LogoutAPIView.as_view(),         name='api_logout'),
    path('auth/me/',               api_views.MeAPIView.as_view(),             name='api_me'),
    path('auth/change-password/',  api_views.ChangePasswordAPIView.as_view(), name='api_change_password'),

    # ── Products ─────────────────────────────────────────────────────────────
    path('products/',              api_views.ProductListCreateAPIView.as_view(),  name='api_products'),
    path('products/types/',        api_views.ProductTypesAPIView.as_view(),       name='api_product_types'),
    path('products/sizes/',        api_views.ProductSizesAPIView.as_view(),       name='api_product_sizes'),
    path('products/<int:pk>/',     api_views.ProductDetailAPIView.as_view(),      name='api_product_detail'),
    path('products/<int:pk>/related/', api_views.ProductRelatedAPIView.as_view(), name='api_product_related'),

    # ── Cart ──────────────────────────────────────────────────────────────────
    path('cart/',                  api_views.CartAPIView.as_view(),       name='api_cart'),
    path('cart/add/<int:pk>/',     api_views.CartAddAPIView.as_view(),    name='api_cart_add'),
    path('cart/update/<int:pk>/',  api_views.CartUpdateAPIView.as_view(), name='api_cart_update'),
    path('cart/remove/<int:pk>/',  api_views.CartRemoveAPIView.as_view(), name='api_cart_remove'),
    path('cart/clear/',            api_views.CartClearAPIView.as_view(),  name='api_cart_clear'),

    # ── Checkout & Orders ─────────────────────────────────────────────────────
    path('checkout/',              api_views.CheckoutAPIView.as_view(),    name='api_checkout'),
    path('orders/',                api_views.OrderListAPIView.as_view(),   name='api_orders'),
    path('orders/<int:pk>/',       api_views.OrderDetailAPIView.as_view(), name='api_order_detail'),

    # ── Promo Codes ───────────────────────────────────────────────────────────
    path('promocodes/',            api_views.PromocodeListCreateAPIView.as_view(), name='api_promocodes'),
    path('promocodes/validate/',   api_views.PromocodeValidateAPIView.as_view(),   name='api_promo_validate'),
    path('promocodes/<int:pk>/',   api_views.PromocodeDetailAPIView.as_view(),     name='api_promo_detail'),

    # ── Admin Dashboard ───────────────────────────────────────────────────────
    path('admin/dashboard/',       api_views.AdminDashboardAPIView.as_view(),      name='api_dashboard'),

    # ── Wishlist ──────────────────────────────────────────────────────────────
    path('wishlist/',                    api_views.WishlistAPIView.as_view(),         name='api_wishlist'),
    path('wishlist/toggle/<int:pk>/',    api_views.WishlistToggleAPIView.as_view(),   name='api_wishlist_toggle'),
    path('wishlist/checkout/',           api_views.WishlistCheckoutAPIView.as_view(), name='api_wishlist_checkout'),

    # ── Ratings ───────────────────────────────────────────────────────────────
    path('products/<int:pk>/ratings/',   api_views.RatingListCreateAPIView.as_view(), name='api_product_ratings'),

    # ── Order status update ───────────────────────────────────────────────────
    path('orders/<int:pk>/status/',      api_views.OrderUpdateStatusAPIView.as_view(), name='api_order_status'),

    # ── Order summary (current user) ─────────────────────────────────────────
    path('orders/summary/',              api_views.OrderSummaryAPIView.as_view(),           name='api_order_summary'),

    # ── Search ───────────────────────────────────────────────────────────────
    path('search/',                      api_views.SearchAPIView.as_view(),                 name='api_search'),

    # ── Admin: User management ────────────────────────────────────────────────
    path('admin/users/',                        api_views.AdminUserListAPIView.as_view(),         name='api_admin_users'),
    path('admin/users/<int:pk>/',               api_views.AdminUserDetailAPIView.as_view(),       name='api_admin_user_detail'),
    path('admin/users/<int:pk>/toggle-active/', api_views.AdminUserToggleActiveAPIView.as_view(), name='api_admin_user_toggle'),

    # ── Admin: Bulk order status update ──────────────────────────────────────
    path('admin/orders/bulk-status/',    api_views.AdminOrderBulkStatusAPIView.as_view(),   name='api_admin_bulk_status'),

    # ── Admin: Promo code toggle ──────────────────────────────────────────────
    path('promocodes/<int:pk>/toggle/',  api_views.AdminPromocodeToggleAPIView.as_view(),   name='api_promo_toggle'),

    # ── Admin: Product CRUD (mirrors admin panel actions) ────────────────────
    path('admin/products/',                          api_views.AdminProductListAPIView.as_view(),        name='api_admin_products'),
    path('admin/products/create/',                   api_views.AdminProductCreateAPIView.as_view(),      name='api_admin_product_create'),
    path('admin/products/<int:pk>/update/',          api_views.AdminProductUpdateAPIView.as_view(),      name='api_admin_product_update'),
    path('admin/products/<int:pk>/delete/',          api_views.AdminProductDeleteAPIView.as_view(),      name='api_admin_product_delete'),
    path('admin/products/<int:pk>/upload-image/',    api_views.AdminProductImageUploadAPIView.as_view(), name='api_admin_product_image'),
]
