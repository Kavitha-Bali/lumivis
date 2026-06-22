from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count
from django.utils.html import format_html
from django.utils.timezone import now, localdate
from .models import Product, transctions, promocode, ratings, Wishlist


# ── Custom admin site with dashboard stats ─────────────────────────────────────

class LumivisAdminSite(admin.AdminSite):
    site_header = "Lumivis Administration"
    site_title  = "Lumivis Admin"
    index_title = "Dashboard"

    def index(self, request, extra_context=None):
        from django.utils.timezone import localdate
        import datetime

        User = get_user_model()
        extra_context = extra_context or {}

        total_revenue = transctions.objects.aggregate(total=Sum('total_price'))['total'] or 0

        today      = localdate()
        month_start = today.replace(day=1)
        monthly_revenue = transctions.objects.filter(
            transaction_date__date__gte=month_start
        ).aggregate(total=Sum('total_price'))['total'] or 0

        orders_by_status = {
            row['status']: row['count']
            for row in transctions.objects.values('status').annotate(count=Count('id'))
        }
        total_orders = transctions.objects.count()

        pending_n    = orders_by_status.get('pending', 0)
        processing_n = orders_by_status.get('processing', 0)
        shipped_n    = orders_by_status.get('shipped', 0)
        delivered_n  = orders_by_status.get('delivered', 0)
        cancelled_n  = orders_by_status.get('cancelled', 0)

        def pct(n):
            return round(n * 100 / total_orders) if total_orders else 0

        top_products = list(
            transctions.objects
            .values('product__id', 'product__name')
            .annotate(units_sold=Sum('quantity'), revenue=Sum('total_price'))
            .order_by('-units_sold')[:6]
        )
        max_sold = top_products[0]['units_sold'] if top_products else 1

        recent_orders = (
            transctions.objects
            .select_related('product', 'user')
            .order_by('-transaction_date')[:8]
        )

        extra_context.update({
            'product_count':      Product.objects.count(),
            'transaction_count':  total_orders,
            'active_promo_count': promocode.objects.filter(is_active=True).count(),
            'user_count':         User.objects.count(),
            'total_revenue':      total_revenue,
            'monthly_revenue':    monthly_revenue,
            'today_orders':       transctions.objects.filter(transaction_date__date=today).count(),
            'wishlist_count':     Wishlist.objects.count(),
            'top_products':       top_products,
            'max_sold':           max_sold,
            'recent_orders':      recent_orders,
            'pending_count':      pending_n,
            'processing_count':   processing_n,
            'shipped_count':      shipped_n,
            'delivered_count':    delivered_n,
            'cancelled_count':    cancelled_n,
            'pending_pct':        pct(pending_n),
            'processing_pct':     pct(processing_n),
            'shipped_pct':        pct(shipped_n),
            'delivered_pct':      pct(delivered_n),
            'cancelled_pct':      pct(cancelled_n),
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
        if obj.image:
            return format_html(
                '<img src="{}" style="width:54px;height:54px;object-fit:cover;'
                'border-radius:8px;border:1px solid #e5e7eb;" />',
                obj.image.url,
            )
        return format_html('<span style="color:#9ca3af;font-size:0.8rem;">No image</span>')


# ── Transactions ─────────────────────────────────────────────────────────────

def _make_status_action(new_status, label):
    def action(modeladmin, request, queryset):
        updated = queryset.update(status=new_status)
        modeladmin.message_user(request, f'{updated} order(s) marked as {label}.')
    action.short_description = f'Mark selected orders as {label}'
    action.__name__ = f'mark_as_{new_status}'
    return action


@admin.register(transctions, site=admin_site)
class TransactionAdmin(admin.ModelAdmin):
    list_display   = ('transaction_id', 'user', 'product', 'quantity', 'total_price', 'transaction_date', 'status_badge')
    list_filter    = ('status', 'transaction_date')
    search_fields  = ('transaction_id', 'product__name', 'user__username')
    ordering       = ('-transaction_date',)
    readonly_fields = ('transaction_date',)
    list_per_page  = 25
    actions        = [
        _make_status_action('processing', 'Processing'),
        _make_status_action('shipped',    'Shipped'),
        _make_status_action('delivered',  'Delivered'),
        _make_status_action('cancelled',  'Cancelled'),
    ]

    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'product', 'quantity', 'total_price', 'status'),
        }),
        ('User & Date', {
            'fields': ('user', 'transaction_date'),
            'classes': ('collapse',),
        }),
    )

    STATUS_COLORS = {
        'pending':    ('#fef3c7', '#92400e'),
        'processing': ('#dbeafe', '#1e40af'),
        'shipped':    ('#ede9fe', '#5b21b6'),
        'delivered':  ('#d1fae5', '#065f46'),
        'cancelled':  ('#fee2e2', '#991b1b'),
    }

    @admin.display(description='Status')
    def status_badge(self, obj):
        bg, fg = self.STATUS_COLORS.get(obj.status, ('#f3f4f6', '#374151'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;'
            'border-radius:20px;font-size:0.75rem;font-weight:600;">{}</span>',
            bg, fg, obj.get_status_display(),
        )


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
                'border-radius:20px;font-size:0.75rem;font-weight:600;">Active</span>'
            )
        return format_html(
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;'
            'border-radius:20px;font-size:0.75rem;font-weight:600;">Inactive</span>'
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


# ── Wishlist ──────────────────────────────────────────────────────────────────

@admin.register(Wishlist, site=admin_site)
class WishlistAdmin(admin.ModelAdmin):
    list_display  = ('user', 'product', 'added_at')
    search_fields = ('user__username', 'product__name')
    ordering      = ('-added_at',)
    readonly_fields = ('added_at',)
    list_per_page = 25
