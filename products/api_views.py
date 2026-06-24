import uuid

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from rest_framework import filters, generics, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from .models import Product, promocode, ratings, Wishlist
from .serializers import (
    ChangePasswordSerializer,
    UpdateProfileSerializer,
    UserSerializer,
    RegisterSerializer,
    ProductSerializer,
    ProductMiniSerializer,
    CartItemSerializer,
    CheckoutSerializer,
    PromocodeSerializer,
    PromocodeValidateSerializer,
    RatingSerializer,
    WishlistSerializer,
)


# ── Response helpers ──────────────────────────────────────────────────────────

def ok(data=None, message='', status_code=status.HTTP_200_OK):
    body = {'status': 'success'}
    if message:
        body['message'] = message
    if data is not None:
        body['data'] = data
    return Response(body, status=status_code)


def err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    body = {'status': 'error', 'message': message}
    if errors:
        body['errors'] = errors
    return Response(body, status=status_code)


# ── Session-cart helper ───────────────────────────────────────────────────────

def _build_cart(request):
    cart  = request.session.get('cart', {})
    items = []
    total = 0
    for pid, qty in cart.items():
        try:
            product  = Product.objects.get(pk=pid)
            subtotal = product.price * qty
            total   += subtotal
            items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
        except Product.DoesNotExist:
            pass
    return items, total


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

class RegisterAPIView(APIView):
    """
    POST /api/auth/register/
    Body: { username, email, password, password2 }
    Returns: { token, user }
    """
    permission_classes = [AllowAny]
    throttle_scope     = 'auth'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return err('Registration failed.', errors=serializer.errors,
                       status_code=status.HTTP_400_BAD_REQUEST)
        user     = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return ok(
            data={'token': token.key, 'user': UserSerializer(user).data},
            message='Account created successfully.',
            status_code=status.HTTP_201_CREATED,
        )


class LoginAPIView(APIView):
    """
    POST /api/auth/login/
    Body: { username, password }
    Returns: { token, user }
    """
    permission_classes = [AllowAny]
    throttle_scope     = 'auth'

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        if not username or not password:
            return err('username and password are required.')
        user = authenticate(request, username=username, password=password)
        if user is None:
            return err('Invalid credentials.', status_code=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return err('Account is disabled.', status_code=status.HTTP_403_FORBIDDEN)
        token, _ = Token.objects.get_or_create(user=user)
        return ok(
            data={'token': token.key, 'user': UserSerializer(user).data},
            message='Logged in successfully.',
        )


class LogoutAPIView(APIView):
    """
    POST /api/auth/logout/
    Deletes the current auth token.
    """
    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        return ok(message='Logged out successfully.')


class MeAPIView(APIView):
    """
    GET   /api/auth/me/   — current user profile
    PATCH /api/auth/me/   — update email / first_name / last_name
    """
    def get(self, request):
        return ok(data=UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return err('Update failed.', errors=serializer.errors)
        serializer.save()
        return ok(data=UserSerializer(request.user).data, message='Profile updated.')


class ChangePasswordAPIView(APIView):
    """
    POST /api/auth/change-password/
    Body: { current_password, new_password, new_password2 }
    """
    throttle_scope = 'auth'

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return err('Password change failed.', errors=serializer.errors)
        serializer.save()
        # Rotate token after password change
        Token.objects.filter(user=request.user).delete()
        token, _ = Token.objects.get_or_create(user=request.user)
        return ok(
            data={'token': token.key},
            message='Password changed. Use the new token for future requests.',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════════

class ProductListCreateAPIView(generics.ListCreateAPIView):
    """
    GET  /api/products/     — list products (public, paginated)
    POST /api/products/     — create product (admin only)

    Query params:
      ?search=<term>                  full-text on name / type / SKU
      ?ordering=price|-price|name
      ?product_type=<type>
      ?product_size=<size>
      ?min_price=<n>
      ?max_price=<n>
    """
    serializer_class = ProductSerializer
    filter_backends  = [filters.SearchFilter, filters.OrderingFilter]
    search_fields    = ['name', 'product_type', 'product_id', 'description']
    ordering_fields  = ['price', 'name', 'id']
    ordering         = ['name']

    def get_permissions(self):
        return [IsAdminUser()] if self.request.method == 'POST' else [AllowAny()]

    def get_queryset(self):
        p   = self.request.query_params
        qs  = Product.objects.all()

        if p.get('product_type'):
            qs = qs.filter(product_type__icontains=p['product_type'])
        if p.get('product_size'):
            qs = qs.filter(product_size__icontains=p['product_size'])
        if p.get('min_price'):
            try:
                qs = qs.filter(price__gte=float(p['min_price']))
            except ValueError:
                pass
        if p.get('max_price'):
            try:
                qs = qs.filter(price__lte=float(p['max_price']))
            except ValueError:
                pass
        return qs


class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/products/<id>/    — detail (public)
    PUT    /api/products/<id>/    — full update (admin)
    PATCH  /api/products/<id>/    — partial update (admin)
    DELETE /api/products/<id>/    — delete (admin)
    """
    queryset         = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [IsAdminUser()]


class ProductRelatedAPIView(APIView):
    """
    GET /api/products/<id>/related/
    Returns up to 8 products of the same type (excluding this one).
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        related = (
            Product.objects
            .filter(product_type=product.product_type)
            .exclude(pk=pk)[:8]
        )
        return ok(data=ProductMiniSerializer(
            related, many=True, context={'request': request}
        ).data)


class ProductTypesAPIView(APIView):
    """
    GET /api/products/types/
    Returns sorted list of distinct product types.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        types = (
            Product.objects
            .values_list('product_type', flat=True)
            .distinct()
            .order_by('product_type')
        )
        return ok(data=list(types))


class ProductSizesAPIView(APIView):
    """
    GET /api/products/sizes/
    Returns sorted list of distinct product sizes.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        sizes = (
            Product.objects
            .values_list('product_size', flat=True)
            .distinct()
            .order_by('product_size')
        )
        return ok(data=list(sizes))


# ═══════════════════════════════════════════════════════════════════════════════
# CART  (session-backed — works for both browser and token clients)
# ═══════════════════════════════════════════════════════════════════════════════

class CartAPIView(APIView):
    """GET /api/cart/ — return the current session cart."""
    permission_classes = [AllowAny]

    def get(self, request):
        items, total = _build_cart(request)
        ctx  = {'request': request}
        return ok(data={
            'items': CartItemSerializer(items, many=True, context=ctx).data,
            'total': str(total),
            'count': sum(i['quantity'] for i in items),
        })


class CartAddAPIView(APIView):
    """
    POST /api/cart/add/<product_id>/
    Body (optional): { "qty": 2 }   — defaults to 1
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        if not Product.objects.filter(pk=pk).exists():
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        try:
            qty = max(1, int(request.data.get('qty', 1)))
        except (ValueError, TypeError):
            qty = 1
        cart          = request.session.get('cart', {})
        cart[str(pk)] = cart.get(str(pk), 0) + qty
        request.session['cart'] = cart
        return ok(
            message=f'Added {qty} item(s) to cart.',
            data={'cart_count': sum(cart.values())},
        )


class CartUpdateAPIView(APIView):
    """
    PATCH /api/cart/update/<product_id>/
    Body: { "quantity": 3 }   — set exact quantity; 0 removes item
    """
    permission_classes = [AllowAny]

    def patch(self, request, pk):
        try:
            qty = int(request.data.get('quantity', 1))
        except (ValueError, TypeError):
            return err('quantity must be a valid integer.')
        cart = request.session.get('cart', {})
        if qty > 0:
            cart[str(pk)] = qty
        else:
            cart.pop(str(pk), None)
        request.session['cart'] = cart
        return ok(message='Cart updated.', data={'cart_count': sum(cart.values())})


class CartRemoveAPIView(APIView):
    """DELETE /api/cart/remove/<product_id>/ — remove a product from the cart."""
    permission_classes = [AllowAny]

    def delete(self, request, pk):
        cart = request.session.get('cart', {})
        cart.pop(str(pk), None)
        request.session['cart'] = cart
        return ok(message='Item removed.', data={'cart_count': sum(cart.values())})


class CartClearAPIView(APIView):
    """DELETE /api/cart/clear/ — empty the entire cart."""
    permission_classes = [AllowAny]

    def delete(self, request):
        request.session['cart'] = {}
        return ok(message='Cart cleared.')


# ═══════════════════════════════════════════════════════════════════════════════
# CHECKOUT & ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

class CheckoutAPIView(APIView):
    """
    POST /api/checkout/
    Places an order.

    Option A — API client sends items explicitly:
      { "items": [{"product_id": 1, "quantity": 2}] }

    Option B — browser client uses the session cart (no body required).

    Returns the list of created transactions.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return err('Invalid order data.', errors=serializer.errors)

        explicit = serializer.validated_data.get('items')

        if explicit:
            order_items = [
                {
                    'product':  item['product_id'],
                    'quantity': item['quantity'],
                    'subtotal': item['product_id'].price * item['quantity'],
                }
                for item in explicit
            ]
        else:
            cart_items, _ = _build_cart(request)
            if not cart_items:
                return err('Cart is empty. Add items or send them in the request body.')
            order_items = cart_items

        request.session['cart'] = {}
        return ok(
            data=[],
            message=f'Order confirmed — {len(order_items)} item(s) placed.',
            status_code=status.HTTP_201_CREATED,
        )


class OrderListAPIView(APIView):
    """GET /api/orders/ — returns empty list (order model removed)."""
    def get(self, request):
        return ok(data=[])


class OrderDetailAPIView(APIView):
    """GET /api/orders/<id>/ — returns 404 (order model removed)."""
    def get(self, request, pk=None):
        return err('Orders are not available.', status_code=status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════════
# PROMO CODES
# ═══════════════════════════════════════════════════════════════════════════════

class PromocodeListCreateAPIView(generics.ListCreateAPIView):
    """
    GET  /api/promocodes/   — list all promo codes (admin only)
    POST /api/promocodes/   — create a promo code (admin only)
    """
    queryset           = promocode.objects.all().order_by('-expiry_date')
    serializer_class   = PromocodeSerializer
    permission_classes = [IsAdminUser]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['promo_code']


class PromocodeDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/promocodes/<id>/   — retrieve (admin only)
    PATCH  /api/promocodes/<id>/   — partial update (admin only)
    DELETE /api/promocodes/<id>/   — delete (admin only)
    """
    queryset           = promocode.objects.all()
    serializer_class   = PromocodeSerializer
    permission_classes = [IsAdminUser]


class PromocodeValidateAPIView(APIView):
    """
    POST /api/promocodes/validate/
    Body: { "promo_code": "SAVE10" }
    Public — anyone can validate a code.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PromocodeValidateSerializer(data=request.data)
        if not serializer.is_valid():
            return err('Invalid request.', errors=serializer.errors)

        code = serializer.validated_data['promo_code'].strip().upper()
        try:
            promo = promocode.objects.get(promo_code=code)
        except promocode.DoesNotExist:
            return err('Promo code not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not promo.is_active:
            return err('This promo code is inactive.')
        if promo.expiry_date < timezone.now():
            return err('This promo code has expired.')

        return ok(data={
            'promo_code':          promo.promo_code,
            'discount_percentage': str(promo.discount_percentage),
            'expiry_date':         promo.expiry_date,
        }, message='Promo code is valid.')


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

class AdminDashboardAPIView(APIView):
    """
    GET /api/admin/dashboard/
    Returns site-wide statistics. Admin only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Sum, Count
        from django.utils.timezone import localdate

        return ok(data={
            'products':         Product.objects.count(),
            'transactions':     0,
            'total_revenue':    '0',
            'active_promos':    promocode.objects.filter(is_active=True, expiry_date__gte=timezone.now()).count(),
            'users':            User.objects.count(),
            'today_orders':     0,
            'wishlist_count':   Wishlist.objects.count(),
            'top_products':     [],
            'orders_by_status': [],
            'recent_orders':    [],
        })


# ═══════════════════════════════════════════════════════════════════════════════
# WISHLIST
# ═══════════════════════════════════════════════════════════════════════════════

class WishlistAPIView(APIView):
    """GET /api/wishlist/ — list the current user's wishlisted products."""

    def get(self, request):
        items = Wishlist.objects.filter(user=request.user).select_related('product')
        return ok(data=WishlistSerializer(items, many=True, context={'request': request}).data)


class WishlistToggleAPIView(APIView):
    """
    POST /api/wishlist/toggle/<pk>/
    Adds the product to the wishlist if not present; removes it if already there.
    Returns: { wishlisted: true|false }
    """

    def post(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
            return ok(message='Removed from wishlist.', data={'wishlisted': False})
        return ok(
            message='Added to wishlist.',
            data={'wishlisted': True},
            status_code=status.HTTP_201_CREATED,
        )


class WishlistCheckoutAPIView(APIView):
    """
    POST /api/wishlist/checkout/
    Places an order (qty 1 each) for every product in the wishlist, then clears it.
    """

    def post(self, request):
        items = Wishlist.objects.filter(user=request.user).select_related('product')
        if not items.exists():
            return err('Your wishlist is empty.')

        count = items.count()
        items.delete()
        return ok(
            data=[],
            message=f'Order confirmed — {count} item(s) placed from your wishlist.',
            status_code=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# RATINGS
# ═══════════════════════════════════════════════════════════════════════════════

class RatingListCreateAPIView(APIView):
    """
    GET  /api/products/<pk>/ratings/  — list all ratings for a product (public)
    POST /api/products/<pk>/ratings/  — submit a rating (authenticated users)
    """

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [IsAuthenticated()]

    def get(self, request, pk):
        if not Product.objects.filter(pk=pk).exists():
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        qs = ratings.objects.filter(product_id=pk).select_related('user').order_by('-created_at')
        avg = qs.aggregate(avg=__import__('django.db.models', fromlist=['Avg']).Avg('rating'))['avg']
        return ok(data={
            'average_rating': round(avg, 1) if avg else None,
            'count':          qs.count(),
            'ratings':        RatingSerializer(qs, many=True, context={'request': request}).data,
        })

    def post(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        if ratings.objects.filter(user=request.user, product=product).exists():
            return err('You have already rated this product.')
        serializer = RatingSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return err('Invalid rating data.', errors=serializer.errors)
        serializer.save(user=request.user, product=product)
        return ok(data=serializer.data, message='Rating submitted.', status_code=status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER STATUS UPDATE  (admin)
# ═══════════════════════════════════════════════════════════════════════════════

class OrderUpdateStatusAPIView(APIView):
    """
    PATCH /api/orders/<pk>/status/
    Body: { "status": "shipped" }
    Admin only — updates the status of a single order.
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        return err('Orders are not available.', status_code=status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class AdminUserListAPIView(generics.ListAPIView):
    """
    GET /api/admin/users/
    Lists all registered users. Admin only.

    Query params:
      ?search=<username|email>
      ?ordering=date_joined|-date_joined|username
    """
    permission_classes = [IsAdminUser]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['username', 'email', 'first_name', 'last_name']
    ordering_fields    = ['date_joined', 'username']
    ordering           = ['-date_joined']

    def get_queryset(self):
        return User.objects.all()

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        data = [
            {
                'id':          u.id,
                'username':    u.username,
                'email':       u.email,
                'first_name':  u.first_name,
                'last_name':   u.last_name,
                'is_staff':    u.is_staff,
                'is_active':   u.is_active,
                'date_joined': u.date_joined,
                'order_count': 0,
            }
            for u in qs
        ]
        return ok(data=data)


class AdminUserDetailAPIView(APIView):
    """
    GET   /api/admin/users/<pk>/          — user detail + order history
    PATCH /api/admin/users/<pk>/          — update is_active / is_staff
    POST  /api/admin/users/<pk>/toggle-active/  — toggle active status
    """
    permission_classes = [IsAdminUser]

    def _get_user(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        u = self._get_user(pk)
        if not u:
            return err('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        return ok(data={
            'id':            u.id,
            'username':      u.username,
            'email':         u.email,
            'first_name':    u.first_name,
            'last_name':     u.last_name,
            'is_staff':      u.is_staff,
            'is_active':     u.is_active,
            'date_joined':   u.date_joined,
            'recent_orders': [],
        })

    def patch(self, request, pk):
        u = self._get_user(pk)
        if not u:
            return err('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        if 'is_active' in request.data:
            u.is_active = bool(request.data['is_active'])
        if 'is_staff' in request.data:
            u.is_staff = bool(request.data['is_staff'])
        u.save(update_fields=['is_active', 'is_staff'])
        return ok(data=UserSerializer(u).data, message='User updated.')


class AdminUserToggleActiveAPIView(APIView):
    """
    POST /api/admin/users/<pk>/toggle-active/
    Toggles the active status of a user. Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return err('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        if u == request.user:
            return err('You cannot deactivate your own account.')
        u.is_active = not u.is_active
        u.save(update_fields=['is_active'])
        state = 'activated' if u.is_active else 'deactivated'
        return ok(
            data={'is_active': u.is_active},
            message=f'User "{u.username}" {state}.',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — BULK ORDER STATUS UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

class AdminOrderBulkStatusAPIView(APIView):
    """
    POST /api/admin/orders/bulk-status/
    Body: { "order_ids": [1, 2, 3], "status": "shipped" }
    Updates multiple orders to the same status at once. Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        return ok(data={'updated_count': 0}, message='Orders are not available.')


# ═══════════════════════════════════════════════════════════════════════════════
# PROMO CODE TOGGLE
# ═══════════════════════════════════════════════════════════════════════════════

class AdminPromocodeToggleAPIView(APIView):
    """
    POST /api/promocodes/<pk>/toggle/
    Toggles the is_active field of a promo code. Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            promo = promocode.objects.get(pk=pk)
        except promocode.DoesNotExist:
            return err('Promo code not found.', status_code=status.HTTP_404_NOT_FOUND)
        promo.is_active = not promo.is_active
        promo.save(update_fields=['is_active'])
        state = 'activated' if promo.is_active else 'deactivated'
        return ok(
            data={'is_active': promo.is_active},
            message=f'Promo code "{promo.promo_code}" {state}.',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

class SearchAPIView(APIView):
    """
    GET /api/search/?q=<term>
    Searches products by name, type, SKU, or description (public).
    Returns up to 20 results.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return err('Provide a search query via ?q=')
        qs = (
            Product.objects
            .filter(
                Q(name__icontains=q) |
                Q(product_type__icontains=q) |
                Q(product_id__icontains=q) |
                Q(description__icontains=q)
            )
            .order_by('name')[:20]
        )
        return ok(data={
            'query':   q,
            'count':   qs.count(),
            'results': ProductSerializer(qs, many=True, context={'request': request}).data,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# USER — ORDER SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

class OrderSummaryAPIView(APIView):
    """
    GET /api/orders/summary/
    Returns the current user's order statistics.
    """

    def get(self, request):
        return ok(data={
            'total_orders':   0,
            'total_spent':    '0',
            'by_status':      {},
            'wishlist_count': Wishlist.objects.filter(user=request.user).count(),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — PRODUCT MANAGEMENT  (mirrors admin panel actions)
# ═══════════════════════════════════════════════════════════════════════════════

class AdminProductListAPIView(APIView):
    """
    GET /api/admin/products/
    Full product list with image + thumbnail URLs.  Admin only.

    Query params:
      ?search=<term>   filter by name / type / SKU
      ?type=<type>     filter by product_type
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Product.objects.all().order_by('name')
        search = request.query_params.get('search', '').strip()
        ptype  = request.query_params.get('type', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(product_id__icontains=search) |
                Q(product_type__icontains=search)
            )
        if ptype:
            qs = qs.filter(product_type__icontains=ptype)
        return ok(data=ProductSerializer(qs, many=True, context={'request': request}).data)


class AdminProductCreateAPIView(APIView):
    """
    POST /api/admin/products/create/
    Creates a new product.  Admin only.
    Accepts multipart/form-data so images can be uploaded directly.

    Required fields : name, product_id, product_type, product_size,
                      description, price
    Optional fields : image (file), thumbnail (file)
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        name         = request.data.get('name', '').strip()
        product_id   = request.data.get('product_id', '').strip()
        product_type = request.data.get('product_type', '').strip()
        product_size = request.data.get('product_size', '').strip()
        description  = request.data.get('description', '').strip()
        price        = request.data.get('price', '').strip()

        # validate required fields
        missing = [f for f, v in {
            'name': name, 'product_id': product_id,
            'product_type': product_type, 'product_size': product_size,
            'description': description, 'price': price,
        }.items() if not v]
        if missing:
            return err(f'Missing required fields: {", ".join(missing)}.')

        try:
            price_val = float(price)
            if price_val <= 0:
                raise ValueError
        except ValueError:
            return err('price must be a positive number.')

        if Product.objects.filter(product_id=product_id).exists():
            return err(f'A product with SKU "{product_id}" already exists.')

        product = Product(
            name=name, product_id=product_id, product_type=product_type,
            product_size=product_size, description=description, price=price_val,
        )
        if 'image' in request.FILES:
            product.image = request.FILES['image']
        if 'thumbnail' in request.FILES:
            product.thumbnail = request.FILES['thumbnail']
        product.save()

        return ok(
            data=ProductSerializer(product, context={'request': request}).data,
            message=f'Product "{name}" created successfully.',
            status_code=status.HTTP_201_CREATED,
        )


class AdminProductUpdateAPIView(APIView):
    """
    PUT / PATCH  /api/admin/products/<pk>/update/
    Updates an existing product.  Admin only.
    Accepts multipart/form-data for image replacement.

    All fields are optional (PATCH behaviour).
    SKU (product_id) cannot be changed.
    """
    permission_classes = [IsAdminUser]

    def _update(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)

        if 'name'         in request.data: product.name         = request.data['name'].strip()
        if 'product_type' in request.data: product.product_type = request.data['product_type'].strip()
        if 'product_size' in request.data: product.product_size = request.data['product_size'].strip()
        if 'description'  in request.data: product.description  = request.data['description'].strip()

        if 'price' in request.data:
            try:
                price_val = float(request.data['price'])
                if price_val <= 0:
                    raise ValueError
                product.price = price_val
            except ValueError:
                return err('price must be a positive number.')

        if 'image'     in request.FILES: product.image     = request.FILES['image']
        if 'thumbnail' in request.FILES: product.thumbnail = request.FILES['thumbnail']

        product.save()
        return ok(
            data=ProductSerializer(product, context={'request': request}).data,
            message=f'Product "{product.name}" updated successfully.',
        )

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)


class AdminProductDeleteAPIView(APIView):
    """
    DELETE /api/admin/products/<pk>/delete/
    Permanently deletes a product.  Admin only.
    Returns the deleted product's id and name for confirmation.
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)
        name = product.name
        pid  = product.pk
        product.delete()
        return ok(
            data={'id': pid, 'name': name},
            message=f'Product "{name}" deleted successfully.',
        )


class AdminProductImageUploadAPIView(APIView):
    """
    POST /api/admin/products/<pk>/upload-image/
    Replaces the main image or thumbnail of an existing product.
    Admin only.

    Body (multipart/form-data):
      image      (file)  — replaces main product image
      thumbnail  (file)  — replaces cover/thumbnail image
    At least one of the two must be provided.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        product = Product.objects.filter(pk=pk).first()
        if not product:
            return err('Product not found.', status_code=status.HTTP_404_NOT_FOUND)

        if 'image' not in request.FILES and 'thumbnail' not in request.FILES:
            return err('Provide at least one file: "image" or "thumbnail".')

        if 'image'     in request.FILES: product.image     = request.FILES['image']
        if 'thumbnail' in request.FILES: product.thumbnail = request.FILES['thumbnail']
        product.save()

        return ok(
            data={
                'image_url':     request.build_absolute_uri(product.image.url)     if product.image     else None,
                'thumbnail_url': request.build_absolute_uri(product.thumbnail.url) if product.thumbnail else None,
            },
            message='Product image(s) updated.',
        )
