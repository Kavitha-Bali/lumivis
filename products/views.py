import uuid

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from .models import Product, transctions, Wishlist, promocode



# ── Helpers ───────────────────────────────────────────────────────────────────

def _cart_items(request):
    """Return (items list, total) from the session cart."""
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


# ── Storefront ────────────────────────────────────────────────────────────────

def home(request):
    """
    Homepage — product grid with optional keyword search.
    GET /?q=<term>
    """
    query    = request.GET.get('q', '').strip()
    products = Product.objects.all()
    if query:
        products = products.filter(name__icontains=query)
    product_types = (
        Product.objects
        .values_list('product_type', flat=True)
        .distinct()
        .order_by('product_type')
    )
    wishlisted_ids = set()
    if request.user.is_authenticated:
        wishlisted_ids = set(
            Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
        )
    return render(request, 'products/index.html', {
        'products':       products,
        'query':          query,
        'product_types':  product_types,
        'wishlisted_ids': wishlisted_ids,
    })


def product_detail(request, pk):
    """
    Single product page with up to 4 related products of the same type.
    GET /product/<pk>/
    """
    product = get_object_or_404(Product, pk=pk)
    related = (
        Product.objects
        .filter(product_type=product.product_type)
        .exclude(pk=pk)[:4]
    )
    is_wishlisted = (
        request.user.is_authenticated and
        Wishlist.objects.filter(user=request.user, product=product).exists()
    )
    return render(request, 'products/product_detail.html', {
        'product':       product,
        'related':       related,
        'is_wishlisted': is_wishlisted,
    })


# ── Cart ──────────────────────────────────────────────────────────────────────

def cart_view(request):
    """
    Shopping cart page.
    GET /cart/
    """
    items, total = _cart_items(request)
    return render(request, 'products/cart.html', {
        'items': items,
        'total': total,
    })


def add_to_cart(request, pk):
    """
    Add one unit of a product to the session cart, then redirect.
    POST /cart/add/<pk>/   (next=<url_name> in POST body redirects back to caller)
    """
    get_object_or_404(Product, pk=pk)
    cart         = request.session.get('cart', {})
    cart[str(pk)] = cart.get(str(pk), 0) + 1
    request.session['cart'] = cart
    messages.success(request, 'Item added to cart.')
    return redirect(request.POST.get('next') or 'home')


def remove_from_cart(request, pk):
    """
    Remove a product entirely from the session cart.
    POST /cart/remove/<pk>/
    """
    cart = request.session.get('cart', {})
    cart.pop(str(pk), None)
    request.session['cart'] = cart
    return redirect('cart')


def update_cart(request, pk):
    """
    Set an exact quantity for a cart item.
    POST /cart/update/<pk>/  body: quantity=<n>
    Quantity ≤ 0 removes the item.
    """
    if request.method == 'POST':
        try:
            qty = int(request.POST.get('quantity', 1))
        except ValueError:
            qty = 1
        cart = request.session.get('cart', {})
        if qty > 0:
            cart[str(pk)] = qty
        else:
            cart.pop(str(pk), None)
        request.session['cart'] = cart
    return redirect('cart')


# ── Checkout ──────────────────────────────────────────────────────────────────

def checkout(request):
    """
    GET  /checkout/  — show order summary + shipping form.
    POST /checkout/  — place order, clear cart, redirect to success page.
    Redirects to /cart/ if cart is empty.
    """
    items, total = _cart_items(request)
    if not items:
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    if request.method == 'POST':
        user = request.user if request.user.is_authenticated else None
        for item in items:
            transctions.objects.create(
                user=user,
                transaction_id=uuid.uuid4().hex[:12].upper(),
                product=item['product'],
                quantity=item['quantity'],
                total_price=item['subtotal'],
            )
        request.session['cart'] = {}
        messages.success(request, 'Order placed successfully!')
        return redirect('order_success')

    return render(request, 'products/checkout.html', {
        'items': items,
        'total': total,
    })


def order_success(request):
    """
    Order confirmation page.
    GET /order-success/
    """
    return render(request, 'products/order_success.html')


# ── Auth ──────────────────────────────────────────────────────────────────────

def register_view(request):
    """
    GET  /register/  — registration form.
    POST /register/  — create account, auto-login, redirect home.
    Redirects to home if already authenticated.
    """
    if request.user.is_authenticated:
        return redirect('home')
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome to Lumivis, {user.username}!')
        return redirect('home')
    return render(request, 'products/register.html', {'form': form})


def login_view(request):
    """
    GET  /login/  — login form.
    POST /login/  — authenticate and redirect to ?next= or home.
    Redirects to home if already authenticated.
    """
    if request.user.is_authenticated:
        return redirect('home')
    form = AuthenticationForm(data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f'Welcome back, {user.username}!')
        return redirect(request.GET.get('next') or 'home')
    return render(request, 'products/login.html', {'form': form})


def logout_view(request):
    """
    POST /logout/  — log out and redirect home.
    """
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


# ── User Panel ────────────────────────────────────────────────────────────────

@login_required
def profile(request):
    """
    GET /profile/  — user dashboard with order history and total spend.
    Requires login (redirects to /login/ if anonymous).
    """
    orders = (
        transctions.objects
        .filter(user=request.user)
        .select_related('product')
        .order_by('-transaction_date')
    )
    total_spent = sum(o.total_price for o in orders)
    return render(request, 'products/profile.html', {
        'orders':      orders,
        'total_spent': total_spent,
    })


# ── Wishlist ──────────────────────────────────────────────────────────────────

@login_required
def wishlist_view(request):
    """
    GET /wishlist/  — show the current user's liked products.
    """
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request, 'products/wishlist.html', {'items': items})


def toggle_wishlist(request, pk):
    """
    POST /wishlist/toggle/<pk>/  — add or remove a product from the wishlist.
    Redirects to ?next= or the wishlist page.
    """
    if not request.user.is_authenticated:
        messages.warning(request, 'Please log in to save products to your wishlist.')
        return redirect('login')
    product  = get_object_or_404(Product, pk=pk)
    existing = Wishlist.objects.filter(user=request.user, product=product).first()
    if existing:
        existing.delete()
        messages.info(request, f'"{product.name}" removed from your wishlist.')
    else:
        Wishlist.objects.create(user=request.user, product=product)
        messages.success(request, f'"{product.name}" added to your wishlist.')
    next_url = request.POST.get('next', '').strip()
    return redirect(next_url if next_url.startswith('/') else 'wishlist')


@login_required
def wishlist_checkout(request):
    """
    POST /wishlist/checkout/  — place orders (qty 1) for every wishlisted product.
    """
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    if not items.exists():
        messages.warning(request, 'Your wishlist is empty.')
        return redirect('wishlist')
    for item in items:
        transctions.objects.create(
            user=request.user,
            transaction_id=uuid.uuid4().hex[:12].upper(),
            product=item.product,
            quantity=1,
            total_price=item.product.price,
        )
    items.delete()
    messages.success(request, 'Your wishlist order has been placed successfully!')
    return redirect('order_success')


# ── Admin Panel ────────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def admin_panel(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('home')
    section       = request.GET.get('s', 'dashboard')
    status_filter = request.GET.get('status', '').strip()

    # ── POST handlers ──────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        # Order status update
        if action == 'update_order':
            order_id   = request.POST.get('order_id', '').strip()
            new_status = request.POST.get('new_status', '').strip()
            valid_statuses = [c[0] for c in transctions.STATUS_CHOICES]
            if order_id and new_status in valid_statuses:
                transctions.objects.filter(pk=order_id).update(status=new_status)
                messages.success(request, 'Order status updated.')
            return redirect(f"{request.path}?s=orders&status={status_filter}")

        # Add product
        if action == 'add_product':
            name         = request.POST.get('name', '').strip()
            product_id   = request.POST.get('product_id', '').strip()
            product_type = request.POST.get('product_type', '').strip()
            product_size = request.POST.get('product_size', '').strip()
            description  = request.POST.get('description', '').strip()
            price        = request.POST.get('price', '').strip()
            if not all([name, product_id, product_type, product_size, description, price]):
                messages.error(request, 'All fields except images are required.')
                return redirect(f"{request.path}?s=add_product")
            if Product.objects.filter(product_id=product_id).exists():
                messages.error(request, f'SKU "{product_id}" already exists.')
                return redirect(f"{request.path}?s=add_product")
            p = Product(
                name=name, product_id=product_id, product_type=product_type,
                product_size=product_size, description=description, price=price,
            )
            if 'image' in request.FILES:
                p.image = request.FILES['image']
            if 'thumbnail' in request.FILES:
                p.thumbnail = request.FILES['thumbnail']
            p.save()
            messages.success(request, f'Product "{name}" added successfully.')
            return redirect(f"{request.path}?s=products")

        # Edit product
        if action == 'edit_product':
            pk           = request.POST.get('pk', '').strip()
            p            = get_object_or_404(Product, pk=pk)
            p.name         = request.POST.get('name', '').strip()
            p.product_type = request.POST.get('product_type', '').strip()
            p.product_size = request.POST.get('product_size', '').strip()
            p.description  = request.POST.get('description', '').strip()
            p.price        = request.POST.get('price', '').strip()
            if 'image' in request.FILES:
                p.image = request.FILES['image']
            if 'thumbnail' in request.FILES:
                p.thumbnail = request.FILES['thumbnail']
            p.save()
            messages.success(request, f'Product "{p.name}" updated.')
            return redirect(f"{request.path}?s=products")

        # Delete product
        if action == 'delete_product':
            pk = request.POST.get('pk', '').strip()
            p  = get_object_or_404(Product, pk=pk)
            name = p.name
            p.delete()
            messages.success(request, f'Product "{name}" deleted.')
            return redirect(f"{request.path}?s=products")

    orders_qs = transctions.objects.select_related('product', 'user').order_by('-transaction_date')
    if status_filter:
        orders_qs = orders_qs.filter(status=status_filter)

    by_status = {
        row['status']: row['count']
        for row in transctions.objects.values('status').annotate(count=Count('id'))
    }
    top_products = (
        transctions.objects
        .values('product__id', 'product__name', 'product__price')
        .annotate(units_sold=Sum('quantity'), revenue=Sum('total_price'))
        .order_by('-units_sold')[:5]
    )

    edit_product = None
    if section == 'edit_product':
        edit_pk = request.GET.get('pk', '').strip()
        if edit_pk:
            edit_product = get_object_or_404(Product, pk=edit_pk)

    return render(request, 'products/admin_panel.html', {
        'section':        section,
        'status_filter':  status_filter,
        'status_choices': transctions.STATUS_CHOICES,
        'orders':         orders_qs[:60],
        'recent_orders':  transctions.objects.select_related('product', 'user').order_by('-transaction_date')[:8],
        'products':       Product.objects.order_by('name'),
        'users':          User.objects.order_by('-date_joined')[:30],
        'promos':         promocode.objects.order_by('-expiry_date'),
        'top_products':   top_products,
        'edit_product':   edit_product,
        'stats': {
            'order_count':    transctions.objects.count(),
            'revenue':        transctions.objects.aggregate(t=Sum('total_price'))['t'] or 0,
            'today_orders':   transctions.objects.filter(transaction_date__date=localdate()).count(),
            'product_count':  Product.objects.count(),
            'user_count':     User.objects.count(),
            'pending_count':  by_status.get('pending', 0),
            'delivered_count': by_status.get('delivered', 0),
            'wishlist_count': Wishlist.objects.count(),
        },
        'by_status': by_status,
    })


# ── User Panel ─────────────────────────────────────────────────────────────────

@login_required
def user_panel(request):
    tab = request.GET.get('tab', 'orders')

    # Profile update
    if request.method == 'POST' and 'update_profile' in request.POST:
        request.user.email      = request.POST.get('email', '').strip()
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name', '').strip()
        request.user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect(f"{request.path}?tab=settings")

    # Password change
    if request.method == 'POST' and 'change_password' in request.POST:
        current  = request.POST.get('current_password', '')
        new_pw   = request.POST.get('new_password', '')
        confirm  = request.POST.get('confirm_password', '')
        if not request.user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
        elif new_pw != confirm:
            messages.error(request, 'New passwords do not match.')
        elif len(new_pw) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
        else:
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully.')
        return redirect(f"{request.path}?tab=settings")

    orders      = transctions.objects.filter(user=request.user).select_related('product').order_by('-transaction_date')
    wishlist    = Wishlist.objects.filter(user=request.user).select_related('product')
    total_spent = orders.aggregate(t=Sum('total_price'))['t'] or 0

    return render(request, 'products/user_panel.html', {
        'tab':         tab,
        'orders':      orders,
        'wishlist':    wishlist,
        'total_spent': total_spent,
        'status_choices': transctions.STATUS_CHOICES,
    })
