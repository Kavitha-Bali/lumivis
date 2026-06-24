import re
import uuid

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Product, Wishlist, promocode



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

def about(request):
    return render(request, 'products/about.html')

def contact(request):
    if request.method == 'POST':
        messages.success(request, "Thank you! We'll get back to you shortly.")
        return redirect('contact')
    return render(request, 'products/contact.html')

def products_page(request):
    query       = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type', '').strip()
    products    = Product.objects.all()
    if query:
        products = products.filter(name__icontains=query)
    if type_filter:
        products = products.filter(product_type__iexact=type_filter)
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
    return render(request, 'products/products_page.html', {
        'products':       products,
        'query':          query,
        'type_filter':    type_filter,
        'product_types':  product_types,
        'wishlisted_ids': wishlisted_ids,
    })

def home(request):
    """
    Homepage — product grid with optional keyword search.
    GET /?q=<term>
    """
    query    = request.GET.get('q', '').strip()
    products = Product.objects.all()
    if query:
        products = products.filter(name__icontains=query)
    products = products.order_by('product_type', 'name')
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


def buy_now(request, pk):
    """
    POST /cart/buy/<pk>/  — add item to cart then go straight to checkout.
    Replaces the old direct link that skipped adding the item.
    """
    get_object_or_404(Product, pk=pk)
    cart          = request.session.get('cart', {})
    cart[str(pk)] = cart.get(str(pk), 0) + 1
    request.session['cart'] = cart
    return redirect('checkout')


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
    POST /checkout/  — validate, place order, store details in session, redirect to success.
    Redirects to /cart/ if cart is empty.
    """
    items, total = _cart_items(request)
    if not items:
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()

        # Phone must be +91 followed by exactly 10 digits
        if not re.match(r'^\+91[6-9][0-9]{9}$', phone):
            messages.error(request, 'Phone number must start with +91 followed by 10 digits (e.g. +919876543210).')
            return render(request, 'products/checkout.html', {
                'items': items, 'total': total,
                'form_data': request.POST,
            })

        # Urgent delivery
        urgent_delivery = request.POST.get('urgent_delivery', 'no') == 'yes'
        delivery_date   = request.POST.get('delivery_date', '').strip()
        try:
            urgent_charge = int(request.POST.get('urgent_charge', '0'))
        except ValueError:
            urgent_charge = 0
        if urgent_charge < 0:
            urgent_charge = 0

        final_total = total + urgent_charge

        # Build order summary for WhatsApp
        order_id = 'LVP-' + uuid.uuid4().hex[:6].upper()
        items_text = '\n'.join(
            f"  • {i['product'].name} ×{i['quantity']} — ₹{i['subtotal']}"
            for i in items
        )

        # Store order details in session for the success page
        request.session['order_id']            = order_id
        request.session['order_total']         = str(final_total)
        request.session['order_customer']      = request.POST.get('full_name', '').strip()
        request.session['order_phone']         = phone
        request.session['order_items']         = items_text
        request.session['order_urgent']        = urgent_delivery
        request.session['order_delivery_date'] = delivery_date if urgent_delivery else ''
        request.session['order_urgent_charge'] = str(urgent_charge) if urgent_delivery else '0'
        request.session['cart']                = {}

        messages.success(request, f'Order {order_id} placed successfully!')
        return redirect('order_success')

    return render(request, 'products/checkout.html', {
        'items': items,
        'total': total,
        'form_data': {},
    })


def order_success(request):
    """
    Order confirmation page — reads order details from session and clears them.
    GET /order-success/
    """
    order_id            = request.session.pop('order_id',            'LVP-UNKNOWN')
    order_total         = request.session.pop('order_total',         '0')
    order_customer      = request.session.pop('order_customer',      '')
    order_phone         = request.session.pop('order_phone',         '')
    order_items         = request.session.pop('order_items',         '')
    order_urgent        = request.session.pop('order_urgent',        False)
    order_delivery_date = request.session.pop('order_delivery_date', '')
    order_urgent_charge = request.session.pop('order_urgent_charge', '0')

    return render(request, 'products/order_success.html', {
        'order_id':            order_id,
        'order_total':         order_total,
        'order_customer':      order_customer,
        'order_phone':         order_phone,
        'order_items':         order_items,
        'order_urgent':        order_urgent,
        'order_delivery_date': order_delivery_date,
        'order_urgent_charge': order_urgent_charge,
    })


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
    return render(request, 'products/profile.html', {
        'orders':      [],
        'total_spent': 0,
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

        # Order status update (orders removed)
        if action == 'update_order':
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

    edit_product = None
    if section == 'edit_product':
        edit_pk = request.GET.get('pk', '').strip()
        if edit_pk:
            edit_product = get_object_or_404(Product, pk=edit_pk)

    return render(request, 'products/admin_panel.html', {
        'section':        section,
        'status_filter':  status_filter,
        'status_choices': [],
        'orders':         [],
        'recent_orders':  [],
        'products':       Product.objects.order_by('name'),
        'users':          User.objects.order_by('-date_joined')[:30],
        'promos':         promocode.objects.order_by('-expiry_date'),
        'top_products':   [],
        'edit_product':   edit_product,
        'stats': {
            'order_count':    0,
            'revenue':        0,
            'today_orders':   0,
            'product_count':  Product.objects.count(),
            'user_count':     User.objects.count(),
            'pending_count':  0,
            'delivered_count': 0,
            'wishlist_count': Wishlist.objects.count(),
        },
        'by_status': {},
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

    wishlist    = Wishlist.objects.filter(user=request.user).select_related('product')

    return render(request, 'products/user_panel.html', {
        'tab':            tab,
        'orders':         [],
        'wishlist':       wishlist,
        'total_spent':    0,
        'status_choices': [],
    })


# ── Instant Search ────────────────────────────────────────────────────────────

def search_suggestions(request):
    """GET /search/suggest/?q=term  →  JSON product suggestions for live search."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': [], 'total': 0})
    qs = Product.objects.filter(
        Q(name__icontains=q) | Q(product_type__icontains=q) | Q(description__icontains=q)
    ).order_by('name')
    total = qs.count()
    results = []
    for p in qs[:8]:
        img = ''
        if p.thumbnail:
            img = p.thumbnail.url
        elif p.image:
            img = p.image.url
        results.append({
            'pk':    p.pk,
            'name':  p.name,
            'price': str(p.price),
            'type':  p.product_type,
            'img':   img,
        })
    return JsonResponse({'results': results, 'total': total})
