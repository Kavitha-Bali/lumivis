from .models import Order


def cart(request):
    session_cart = request.session.get('cart', {})
    count = sum(session_cart.values())
    return {'cart_count': count}


def order_notifications(request):
    notifications = []
    if request.user.is_authenticated:
        notifications = list(
            Order.objects.filter(
                user=request.user,
                payment_status__in=['verified', 'rejected'],
                notification_seen=False,
            ).values('order_id', 'payment_status', 'status')
        )
    return {'order_notifications': notifications}
