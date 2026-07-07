from django.contrib import admin
from django.contrib.auth import get_user_model

from django.utils.html import format_html, mark_safe
from django.utils.timezone import now
from .models import Product, PopupOffer, promocode, ratings, Wishlist


# ── Custom admin site with dashboard stats ─────────────────────────────────────

class LumivisAdminSite(admin.AdminSite):
    site_header = "Lumivis Administration"
    site_title  = "Lumivis Admin"
    index_title = "Dashboard"

    def index(self, request, extra_context=None):
        User = get_user_model()
        extra_context = extra_context or {}
        extra_context.update({
            'product_count':      Product.objects.count(),
            'transaction_count':  0,
            'active_promo_count': promocode.objects.filter(is_active=True).count(),
            'user_count':         User.objects.count(),
            'total_revenue':      0,
            'monthly_revenue':    0,
            'today_orders':       0,
            'wishlist_count':     Wishlist.objects.count(),
            'top_products':       [],
            'max_sold':           1,
            'recent_orders':      [],
            'pending_count':      0,
            'processing_count':   0,
            'shipped_count':      0,
            'delivered_count':    0,
            'cancelled_count':    0,
            'pending_pct':        0,
            'processing_pct':     0,
            'shipped_pct':        0,
            'delivered_pct':      0,
            'cancelled_pct':      0,
        })
        return super().index(request, extra_context=extra_context)


admin_site = LumivisAdminSite(name='lumivis_admin')


# ── Product ─────────────────────────────────────────────────────────────────

@admin.register(Product, site=admin_site)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ('image_thumb', 'name', 'product_id', 'product_type', 'product_size', 'price')
    list_display_links = ('name',)
    search_fields = ('name', 'product_id', 'product_type')
    list_filter   = ('product_type', 'product_size')
    ordering      = ('name',)
    list_per_page = 20

    fieldsets = (
        ('Product Information', {
            'fields': ('name', 'product_id', 'product_type', 'product_size', 'description'),
        }),
        ('Pricing & Image', {
            'fields': ('price', 'image', 'image_thumb'),
        }),
    )
    readonly_fields = ('image_thumb',)

    @admin.display(description='Image')
    def image_thumb(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:54px;height:54px;object-fit:cover;'
                'border-radius:8px;border:1px solid #e5e7eb;" />',
                obj.image.url,
            )
        return mark_safe('<span style="color:#9ca3af;font-size:0.8rem;">No image</span>')


# ── Promo Codes ──────────────────────────────────────────────────────────────

@admin.register(promocode, site=admin_site)
class PromocodeAdmin(admin.ModelAdmin):
    list_display  = ('promo_code', 'discount_percentage', 'expiry_date', 'status_badge')
    list_filter   = ('is_active',)
    search_fields = ('promo_code',)
    ordering      = ('-expiry_date',)
    list_per_page = 20

    fieldsets = (
        ('Promo Details', {
            'fields': ('promo_code', 'discount_percentage', 'expiry_date', 'is_active'),
        }),
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        is_expired = obj.expiry_date < now()
        if obj.is_active and not is_expired:
            return format_html(
                '<span style="background:#d1fae5;color:#065f46;padding:3px 10px;'
                'border-radius:20px;font-size:0.75rem;font-weight:600;">{}</span>',
                'Active',
            )
        return format_html(
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;'
            'border-radius:20px;font-size:0.75rem;font-weight:600;">{}</span>',
            'Inactive',
        )


# ── Ratings ──────────────────────────────────────────────────────────────────

@admin.register(ratings, site=admin_site)
class RatingsAdmin(admin.ModelAdmin):
    list_display  = ('product', 'user', 'star_display', 'created_at')
    list_filter   = ('rating',)
    search_fields = ('product__name', 'user__username', 'review')
    ordering      = ('-created_at',)
    readonly_fields = ('created_at',)
    list_per_page = 25

    @admin.display(description='Rating')
    def star_display(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html(
            '<span style="color:#f59e0b;font-size:1rem;letter-spacing:2px;">{}</span>',
            stars,
        )


# ── Popup Offer ──────────────────────────────────────────────────────────────

@admin.register(PopupOffer, site=admin_site)
class PopupOfferAdmin(admin.ModelAdmin):
    list_display        = ('popup_image_thumb', 'featured_product', 'is_active', 'created_at')
    list_display_links  = ('popup_image_thumb',)
    list_filter         = ('is_active',)
    ordering            = ('-created_at',)
    list_per_page       = 20
    readonly_fields     = ('popup_image_thumb',)

    fieldsets = (
        ('Popup Image', {
            'description': 'Upload an image for the popup. Recommended size: 600 × 800 px (portrait).',
            'fields': ('image', 'popup_image_thumb'),
        }),
        ('Buy Now Product  (optional)', {
            'description': 'Select a product to show a Buy Now button on the popup. Leave empty to show the popup without a button.',
            'fields': ('product',),
        }),
        ('Visibility', {
            'fields': ('is_active',),
        }),
    )

    @admin.display(description='Image')
    def popup_image_thumb(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:70px;height:88px;object-fit:cover;'
                'border-radius:8px;border:1px solid #e5e7eb;" />',
                obj.image.url,
            )
        return mark_safe('<span style="color:#9ca3af;font-size:0.8rem;">No image</span>')

    @admin.display(description='Product (Buy Now)')
    def featured_product(self, obj):
        if obj.product:
            return format_html(
                '<span style="font-weight:600;">{}</span>'
                '&nbsp;<span style="color:#6b7280;font-size:.8rem;">₹{}</span>',
                obj.product.name, obj.product.price,
            )
        return mark_safe('<span style="color:#9ca3af;font-size:0.8rem;">—</span>')


# ── Wishlist ──────────────────────────────────────────────────────────────────

@admin.register(Wishlist, site=admin_site)
class WishlistAdmin(admin.ModelAdmin):
    list_display  = ('user', 'product', 'added_at')
    search_fields = ('user__username', 'product__name')
    ordering      = ('-added_at',)
    readonly_fields = ('added_at',)
    list_per_page = 25
