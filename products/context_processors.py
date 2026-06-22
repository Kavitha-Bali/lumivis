def cart(request):
    session_cart = request.session.get('cart', {})
    count = sum(session_cart.values())
    return {'cart_count': count}
