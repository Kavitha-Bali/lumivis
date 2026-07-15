import re
import uuid
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Q, Avg
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt

from django.utils import timezone

from messaging.smtp import send_templated_email

from .storage_backends import _blob_client

from .forms import CustomRegisterForm, ForgotPasswordForm
from .models import CancelRequest, ContactMessage, Order, PopupOffer, Product, ProductImage, UserProfile, Wishlist, promocode, ratings


# ── Media proxy ──────────────────────────────────────────────────────────────

@login_not_required
def serve_media(request, path):
    """Proxy /media/* — streams from Azure, never exposes the blob URL."""
    try:
        download = _blob_client(path).download_blob()
        props = download.properties
        content_type = (props.get('content_settings') or {}).get('content_type') or 'application/octet-stream'
        return StreamingHttpResponse(download.chunks(), content_type=content_type)
    except Exception:
        raise Http404


# ── Access-control decorators ─────────────────────────────────────────────────

def staff_required(view_func):
    """Allow only authenticated staff/admin users. Others are denied with a clear message."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/login/?next={request.path}')
        if not request.user.is_staff:
            messages.error(request, 'Access denied. This area is for administrators only.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper



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
        name    = request.POST.get('name', '').strip()
        email   = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        msg_body = request.POST.get('message', '').strip()
        if name and email and msg_body:
            ContactMessage.objects.create(
                name=name, email=email, subject=subject, message=msg_body
            )
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
    popup_offer = PopupOffer.objects.filter(is_active=True).select_related('product').order_by('-created_at').first()

    return render(request, 'products/index.html', {
        'products':       products,
        'query':          query,
        'product_types':  product_types,
        'wishlisted_ids': wishlisted_ids,
        'popup_offer':    popup_offer,
    })

# @csrf_exempt
def product_detail(request, pk):
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
    product_reviews = ratings.objects.filter(product=product).select_related('user').order_by('-created_at')
    avg_rating      = product_reviews.aggregate(avg=Avg('rating'))['avg']
    user_has_reviewed = (
        request.user.is_authenticated and
        ratings.objects.filter(user=request.user, product=product).exists()
    )
    user_can_review = (
        request.user.is_authenticated and
        not user_has_reviewed and
        Order.objects.filter(
            user=request.user, status='delivered',
            items_text__icontains=product.name,
        ).exists()
    )
    return render(request, 'products/product_detail.html', {
        'product':           product,
        'related':           related,
        'is_wishlisted':     is_wishlisted,
        'reviews':           product_reviews,
        'avg_rating':        avg_rating,
        'review_count':      product_reviews.count(),
        'user_has_reviewed': user_has_reviewed,
        'user_can_review':   user_can_review,
    })


# ── Reviews ───────────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def submit_review(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    if request.method != 'POST':
        return redirect('product_detail', pk=product_pk)

    if ratings.objects.filter(user=request.user, product=product).exists():
        messages.error(request, 'You have already reviewed this product.')
        return redirect('product_detail', pk=product_pk)

    if not Order.objects.filter(
        user=request.user, status='delivered',
        items_text__icontains=product.name,
    ).exists():
        messages.error(request, 'You can only review products from your delivered orders.')
        return redirect('product_detail', pk=product_pk)

    star        = request.POST.get('rating', '').strip()
    review_text = request.POST.get('review', '').strip()

    if not star or not star.isdigit() or int(star) not in range(1, 6):
        messages.error(request, 'Please select a rating between 1 and 5 stars.')
        return redirect('product_detail', pk=product_pk)
    if len(review_text) < 10:
        messages.error(request, 'Review must be at least 10 characters.')
        return redirect('product_detail', pk=product_pk)

    ratings.objects.create(user=request.user, product=product, rating=int(star), review=review_text)
    messages.success(request, f'Thank you! Your review for "{product.name}" has been published.')
    return redirect('product_detail', pk=product_pk)


@login_required(login_url='/login/')
def delete_review(request, review_pk):
    review     = get_object_or_404(ratings, pk=review_pk)
    product_pk = review.product.pk
    if request.method == 'POST':
        if request.user == review.user or request.user.is_staff:
            review.delete()
            if request.user.is_staff:
                messages.success(request, 'Review deleted.')
                return redirect(f"{reverse('admin_panel')}?s=reviews")
            messages.success(request, 'Your review has been removed.')
        else:
            messages.error(request, 'You can only delete your own reviews.')
    return redirect('product_detail', pk=product_pk)


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
    if not request.user.is_authenticated:
        return redirect(reverse('login') + '?next=' + reverse('product_detail', args=[pk]))
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
    if not request.user.is_authenticated:
        return redirect(reverse('login') + '?next=' + reverse('product_detail', args=[pk]))
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


# ── Promo code AJAX validator ──────────────────────────────────────────────────

@login_required(login_url='/login/')
def apply_promo(request):
    if request.method != 'POST':
        return JsonResponse({'valid': False, 'message': 'Invalid request.'})
    code = request.POST.get('code', '').strip()
    if not code:
        return JsonResponse({'valid': False, 'message': 'Please enter a promo code.'})
    try:
        promo = promocode.objects.get(promo_code__iexact=code, is_active=True)
        if promo.expiry_date < timezone.now():
            return JsonResponse({'valid': False, 'message': 'This promo code has expired.'})
        return JsonResponse({
            'valid':        True,
            'discount_pct': float(promo.discount_percentage),
            'code':         promo.promo_code,
            'message':      f'{float(promo.discount_percentage):.0f}% discount applied!',
        })
    except promocode.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid promo code. Please check and try again.'})


# ── Checkout ──────────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
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

        # Delivery zone & charge
        delivery_zone = request.POST.get('delivery_zone', 'inside').strip()
        if delivery_zone not in ('inside', 'outside'):
            delivery_zone = 'inside'
        try:
            delivery_charge = int(request.POST.get('delivery_charge', '100'))
        except ValueError:
            delivery_charge = 100
        if delivery_zone == 'inside':
            delivery_charge = 100
        else:
            delivery_charge = 250

        # Promo code — server-side re-validation (client JS already validated, but we confirm here)
        promo_code_input    = request.POST.get('promo_code', '').strip()
        promo_discount      = Decimal('0')
        promo_code_applied  = ''
        if promo_code_input:
            try:
                promo_obj = promocode.objects.get(promo_code__iexact=promo_code_input, is_active=True)
                if promo_obj.expiry_date >= timezone.now():
                    promo_discount     = (total * promo_obj.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
                    promo_code_applied = promo_obj.promo_code
            except promocode.DoesNotExist:
                pass

        final_total = total - promo_discount + Decimal(urgent_charge) + Decimal(delivery_charge)

        # Build order summary for WhatsApp
        order_id = 'LVP-' + uuid.uuid4().hex[:6].upper()
        items_text = '\n'.join(
            f"  • {i['product'].name} ×{i['quantity']} — ₹{i['subtotal']}"
            for i in items
        )

        customer_name = request.POST.get('full_name', '').strip()

        # Payment screenshot
        screenshot_file = request.FILES.get('payment_screenshot')

        # UPI payment details — both required
        upi_id         = request.POST.get('upi_id', '').strip()
        transaction_id = request.POST.get('transaction_id', '').strip()

        if not upi_id:
            messages.error(request, 'Your UPI ID is required to place an order.')
            return render(request, 'products/checkout.html', {
                'items': items, 'total': total, 'form_data': request.POST,
            })
        if not transaction_id or not re.match(r'^[A-Za-z0-9]{8,20}$', transaction_id):
            messages.error(request, 'A valid Transaction / UTR ID (8–20 characters) is required.')
            return render(request, 'products/checkout.html', {
                'items': items, 'total': total, 'form_data': request.POST,
            })

        # Persist order to database
        order_obj = Order.objects.create(
            order_id        = order_id,
            user            = request.user if request.user.is_authenticated else None,
            customer_name   = customer_name,
            phone           = phone,
            items_text      = items_text,
            total           = final_total,
            urgent          = urgent_delivery,
            delivery_date   = delivery_date if urgent_delivery else '',
            urgent_charge   = urgent_charge if urgent_delivery else 0,
            delivery_zone   = delivery_zone,
            delivery_charge = delivery_charge,
            promo_code      = promo_code_applied,
            promo_discount  = promo_discount,
            upi_id          = upi_id,
            transaction_id  = transaction_id,
            payment_status  = 'pending',
        )
        if screenshot_file:
            order_obj.payment_screenshot = screenshot_file
            order_obj.save()

        # Store order details in session for the success page
        request.session['order_id']              = order_id
        request.session['order_total']           = str(final_total)
        request.session['order_customer']        = customer_name
        request.session['order_phone']           = phone
        request.session['order_items']           = items_text
        request.session['order_urgent']          = urgent_delivery
        request.session['order_delivery_date']   = delivery_date if urgent_delivery else ''
        request.session['order_urgent_charge']   = str(urgent_charge) if urgent_delivery else '0'
        request.session['order_delivery_zone']   = delivery_zone
        request.session['order_delivery_charge'] = str(delivery_charge)
        request.session['order_promo_code']      = promo_code_applied
        request.session['order_promo_discount']  = str(promo_discount)
        request.session['order_screenshot_url']  = order_obj.payment_screenshot.url if order_obj.payment_screenshot else ''
        request.session['order_upi_id']          = upi_id
        request.session['order_transaction_id']  = transaction_id
        request.session['cart']                  = {}

        messages.success(request, f'Order {order_id} placed successfully!')
        return redirect('order_success')

    return render(request, 'products/checkout.html', {
        'items': items,
        'total': total,
        'form_data': {
            'full_name':   '',
            'email':       request.user.email if request.user.is_authenticated else '',
            'phone_input': '+91',
            'address':     '',
            'city':        '',
            'pincode':     '',
        },
    })


def order_success(request):
    """
    Order confirmation page — reads order details from session and clears them.
    GET /order-success/
    """
    order_id              = request.session.pop('order_id',              'LVP-UNKNOWN')
    order_total           = request.session.pop('order_total',           '0')
    order_customer        = request.session.pop('order_customer',        '')
    order_phone           = request.session.pop('order_phone',           '')
    order_items           = request.session.pop('order_items',           '')
    order_urgent          = request.session.pop('order_urgent',          False)
    order_delivery_date   = request.session.pop('order_delivery_date',   '')
    order_urgent_charge   = request.session.pop('order_urgent_charge',   '0')
    order_delivery_zone   = request.session.pop('order_delivery_zone',   'inside')
    order_delivery_charge = request.session.pop('order_delivery_charge', '100')
    order_screenshot_url  = request.session.pop('order_screenshot_url',  '')
    order_upi_id          = request.session.pop('order_upi_id',          '')
    order_transaction_id  = request.session.pop('order_transaction_id',  '')

    delivery_zone_label = 'Inside Visakhapatnam' if order_delivery_zone == 'inside' else 'Outside Visakhapatnam'

    return render(request, 'products/order_success.html', {
        'order_id':              order_id,
        'order_total':           order_total,
        'order_customer':        order_customer,
        'order_phone':           order_phone,
        'order_items':           order_items,
        'order_urgent':          order_urgent,
        'order_delivery_date':   order_delivery_date,
        'order_urgent_charge':   order_urgent_charge,
        'order_delivery_zone':   order_delivery_zone,
        'order_delivery_charge': order_delivery_charge,
        'delivery_zone_label':   delivery_zone_label,
        'order_screenshot_url':  order_screenshot_url,
        'order_upi_id':          order_upi_id,
        'order_transaction_id':  order_transaction_id,
    })


# ── Admin: Approve / Reject Payment ─────────────────────────────────────────

@staff_required
def approve_payment(request, order_id, action):
    order = get_object_or_404(Order, order_id=order_id)
    if action == 'approve':
        order.payment_status = 'verified'
        order.status = 'confirmed'
        order.save()
        messages.success(request, f'Payment verified and order {order_id} confirmed.')
    elif action == 'reject':
        order.payment_status = 'rejected'
        order.save()
        messages.warning(request, f'Payment rejected for order {order_id}.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_panel'))


# ── Dismiss Order Notification ───────────────────────────────────────────────

@login_required(login_url='/login/')
def dismiss_notification(request, order_id):
    if request.method == 'POST':
        Order.objects.filter(order_id=order_id, user=request.user).update(notification_seen=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
    return redirect(request.META.get('HTTP_REFERER', 'home'))


# ── Order Track ──────────────────────────────────────────────────────────────

def order_track(request):
    order = None
    error = None
    searched_id = request.GET.get('order_id', '').strip().upper()
    if searched_id:
        try:
            order = Order.objects.get(order_id=searched_id)
            # User is actively viewing their order — clear the notification
            if request.user.is_authenticated and order.user == request.user and not order.notification_seen:
                order.notification_seen = True
                order.save(update_fields=['notification_seen'])
        except Order.DoesNotExist:
            error = 'No order found with that ID. Please check and try again.'
    return render(request, 'products/order_track.html', {
        'order': order,
        'error': error,
        'searched_id': searched_id,
    })


# ── Order Cancellation ───────────────────────────────────────────────────────

def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)

    if order.status in ('shipped', 'delivered', 'cancelled'):
        messages.error(request, 'This order cannot be cancelled at this stage.')
        return redirect('home')

    already_requested = CancelRequest.objects.filter(order=order).exists()
    if already_requested:
        messages.info(request, 'A cancellation request is already pending for this order.')
        return redirect('home')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for cancellation.')
            return render(request, 'products/cancel_order.html', {'order': order})
        CancelRequest.objects.create(order=order, reason=reason)
        messages.success(request, 'Cancellation request submitted. Admin will review it shortly.')
        return redirect('home')

    return render(request, 'products/cancel_order.html', {'order': order})


@staff_required
def admin_cancel_review(request, pk, action):
    cancel_req = get_object_or_404(CancelRequest, pk=pk)
    if request.method != 'POST':
        return redirect('/admin-panel/?s=cancellations')
    admin_response = request.POST.get('admin_response', '').strip()
    if action == 'approve':
        cancel_req.status        = 'approved'
        cancel_req.reviewed_at   = timezone.now()
        cancel_req.admin_response = admin_response
        cancel_req.save()
        cancel_req.order.status = 'cancelled'
        cancel_req.order.save()
        messages.success(request, f'Order {cancel_req.order.order_id} has been cancelled.')
    elif action == 'reject':
        cancel_req.status        = 'rejected'
        cancel_req.reviewed_at   = timezone.now()
        cancel_req.admin_response = admin_response
        cancel_req.save()
        messages.info(request, f'Cancellation request for {cancel_req.order.order_id} rejected.')
    return redirect('/admin-panel/?s=cancellations')


# ── Auth ──────────────────────────────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = CustomRegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user  = form.save()
        phone = form.cleaned_data.get('phone', '').strip()
        UserProfile.objects.create(user=user, phone=phone)
        login(request, user)
        messages.success(request, f'Welcome to Lumivis, {user.username}!')
        return redirect('home')
    return render(request, 'products/register.html', {'form': form})


@ensure_csrf_cookie
def login_view(request):
    """
    GET  /login/  — login form.
    POST /login/  — authenticate and redirect to ?next= or home.
    """
    # Resolve next URL — prefer GET param, fall back to POST body
    next_url = request.GET.get('next', '').strip() or request.POST.get('next', '').strip()
    # Only allow relative internal redirects (no open-redirect)
    if not next_url.startswith('/'):
        next_url = ''

    if request.user.is_authenticated:
        if next_url:
            return redirect(next_url)
        return redirect('admin_panel' if request.user.is_staff else 'home')

    form = AuthenticationForm(data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f'Welcome back, {user.username}!')
        if next_url:
            return redirect(next_url)
        return redirect('admin_panel' if user.is_staff else 'home')

    return render(request, 'products/login.html', {'form': form, 'next': next_url})


def logout_view(request):
    """
    POST /logout/  — log out and redirect home.
    """
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


def forgot_password_view(request):
    """
    GET  /forgot-password/  — email entry form.
    POST /forgot-password/  — email a reset link via the Samanyastra mailer.
    """
    if request.user.is_authenticated:
        return redirect('home')

    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            # Built from SITE_BASE_URL (not request.build_absolute_uri) — this
            # email is opened outside any request, often on another device, so
            # the logo <img> src must be a publicly reachable URL rather than
            # whatever Host header happened to hit this view (e.g. localhost).
            site_base = settings.SITE_BASE_URL.rstrip('/')
            reset_link = f"{site_base}{reverse('reset_password', args=[uidb64, token])}"
            logo_url = f"{site_base}{static('logoo.png')}"
            send_templated_email(
                template_name='lumivis_forgot_password',
                subject='Reset your Lumivis password',
                recipients=[user.email],
                context={'reset_link': reset_link, 'logo_url': logo_url},
            )
        # Same message whether or not the email is registered — avoids leaking
        # which addresses have accounts.
        messages.success(
            request,
            "If an account exists for that email, we've sent a password reset link."
        )
        return redirect('login')

    return render(request, 'products/forgot_password.html', {'form': form})


def reset_password_view(request, uidb64, token):
    """
    GET  /reset-password/<uidb64>/<token>/  — set-new-password form.
    POST /reset-password/<uidb64>/<token>/  — apply the new password.
    """
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, 'This password reset link is invalid or has expired.')
        return redirect('forgot_password')

    form = SetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your password has been reset. Please sign in.')
        return redirect('login')

    return render(request, 'products/reset_password.html', {'form': form})


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
        return redirect(reverse('login') + '?next=' + reverse('product_detail', args=[pk]))
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

@staff_required
def admin_panel(request):
    section       = request.GET.get('s', 'dashboard')
    status_filter = request.GET.get('status', '').strip()

    # ── POST handlers ──────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'update_order':
            order_pk   = request.POST.get('order_id', '').strip()
            new_status = request.POST.get('new_status', '').strip()
            if order_pk and new_status in dict(Order.STATUS_CHOICES):
                try:
                    o = Order.objects.get(pk=order_pk)
                    o.status = new_status
                    o.save()
                    messages.success(request, f'Order {o.order_id} marked as {new_status}.')
                except Order.DoesNotExist:
                    pass
            back = section if section in ('transactions', 'dashboard') else 'orders'
            return redirect(f"{request.path}?s={back}")

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
            if 'cover_image' in request.FILES:
                p.cover_image = request.FILES['cover_image']
            p.save()
            for gallery_file in request.FILES.getlist('gallery_images'):
                ProductImage.objects.create(product=p, image=gallery_file)
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
            if 'cover_image' in request.FILES:
                p.cover_image = request.FILES['cover_image']
            p.save()
            for gallery_file in request.FILES.getlist('gallery_images'):
                ProductImage.objects.create(product=p, image=gallery_file)
            messages.success(request, f'Product "{p.name}" updated.')
            return redirect(f"{request.path}?s=products")

        # Delete a single gallery image from a product
        if action == 'delete_product_image':
            image_pk = request.POST.get('image_pk', '').strip()
            gallery_image = get_object_or_404(ProductImage, pk=image_pk)
            product_pk = gallery_image.product_id
            gallery_image.delete()
            messages.success(request, 'Gallery image removed.')
            return redirect(f"{request.path}?s=edit_product&pk={product_pk}")

        # Delete product
        if action == 'delete_product':
            pk = request.POST.get('pk', '').strip()
            p  = get_object_or_404(Product, pk=pk)
            name = p.name
            p.delete()
            messages.success(request, f'Product "{name}" deleted.')
            return redirect(f"{request.path}?s=products")

        # Mark contact message as read
        if action == 'mark_message_read':
            msg_pk = request.POST.get('msg_pk', '').strip()
            if msg_pk:
                ContactMessage.objects.filter(pk=msg_pk).update(is_read=True)
            return redirect(f"{request.path}?s=messages")

    edit_product = None
    if section == 'edit_product':
        edit_pk = request.GET.get('pk', '').strip()
        if edit_pk:
            edit_product = get_object_or_404(Product, pk=edit_pk)

    cancel_requests = CancelRequest.objects.select_related('order').order_by('-requested_at')

    orders_qs = Order.objects.order_by('-created_at')
    if status_filter:
        orders_qs = orders_qs.filter(status=status_filter)

    return render(request, 'products/admin_panel.html', {
        'section':          section,
        'status_filter':    status_filter,
        'status_choices':   Order.STATUS_CHOICES,
        'orders':           orders_qs,
        'recent_orders':    Order.objects.order_by('-created_at')[:10],

        'products':         Product.objects.order_by('name'),
        'users':            User.objects.order_by('-date_joined')[:30],
        'promos':           promocode.objects.order_by('-expiry_date'),
        'top_products':     [],
        'edit_product':     edit_product,
        'cancel_requests':  cancel_requests,
        'pending_cancels':  cancel_requests.filter(status='pending').count(),
        'all_ratings':       ratings.objects.select_related('user', 'product').order_by('-created_at'),
        'ratings_count':     ratings.objects.count(),
        'contact_messages':  ContactMessage.objects.order_by('-created_at'),
        'unread_count':      ContactMessage.objects.filter(is_read=False).count(),
        'stats': {
            'order_count':     Order.objects.count(),
            'revenue':         sum(o.total for o in Order.objects.all()),
            'today_orders':    Order.objects.filter(created_at__date=timezone.now().date()).count(),
            'product_count':   Product.objects.count(),
            'user_count':      User.objects.count(),
            'pending_count':   Order.objects.filter(status='pending').count(),
            'confirmed_count': Order.objects.filter(status='confirmed').count(),
            'shipped_count':   Order.objects.filter(status='shipped').count(),
            'delivered_count': Order.objects.filter(status='delivered').count(),
            'cancelled_count': Order.objects.filter(status='cancelled').count(),
            'wishlist_count':  Wishlist.objects.count(),
            'today_revenue':   sum(o.total for o in Order.objects.filter(created_at__date=timezone.now().date())),
        },
        'by_status': {
            'pending':   Order.objects.filter(status='pending').count(),
            'confirmed': Order.objects.filter(status='confirmed').count(),
            'shipped':   Order.objects.filter(status='shipped').count(),
            'delivered': Order.objects.filter(status='delivered').count(),
            'cancelled': Order.objects.filter(status='cancelled').count(),
        },
    })


# ── User Panel ─────────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def user_panel(request):
    if request.user.is_staff:
        return redirect('admin_panel')
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
    orders      = Order.objects.filter(user=request.user).select_related('cancel_request').order_by('-created_at')
    total_spent = sum(o.total for o in orders)

    # Reviews data
    user_reviews = ratings.objects.filter(user=request.user).select_related('product').order_by('-created_at')
    reviewed_pids = set(user_reviews.values_list('product_id', flat=True))

    # Products from delivered orders that the user hasn't reviewed yet
    delivered_orders = Order.objects.filter(user=request.user, status='delivered')
    delivered_names  = set()
    for o in delivered_orders:
        for name in re.findall(r'• (.+?) ×\d', o.items_text):
            delivered_names.add(name.strip())
    can_review_products = list(
        Product.objects.filter(name__in=delivered_names).exclude(pk__in=reviewed_pids)
    ) if delivered_names else []

    return render(request, 'products/user_panel.html', {
        'tab':                  tab,
        'orders':               orders,
        'wishlist':             wishlist,
        'total_spent':          total_spent,
        'status_choices':       [],
        'user_reviews':         user_reviews,
        'can_review_products':  can_review_products,
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
