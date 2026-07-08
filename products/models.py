from django.db import models
from django.contrib.auth.models import User


class Product(models.Model):
    name = models.CharField(max_length=100)
    product_id = models.CharField(max_length=50, unique=True)
    product_type = models.CharField(max_length=50)
    product_size = models.CharField(max_length=50)
    thumbnail   = models.ImageField(upload_to='products/thumb/',  null=True, blank=True)
    cover_image = models.ImageField(upload_to='products/covers/', null=True, blank=True)
    description = models.TextField()
    price       = models.DecimalField(max_digits=10, decimal_places=2)
    image       = models.ImageField(upload_to='products/', null=True, blank=True)

    def __str__(self):
        return self.name



class ratings(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    review = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"


class promocode(models.Model):
    promo_code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    expiry_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.promo_code


class UserProfile(models.Model):
    user  = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"{self.user.username} profile"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped',   'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending',  'Pending Verification'),
        ('verified', 'Payment Verified'),
        ('rejected', 'Payment Rejected'),
    ]
    order_id       = models.CharField(max_length=20, unique=True)
    user           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    customer_name  = models.CharField(max_length=100)
    phone          = models.CharField(max_length=20)
    items_text     = models.TextField()
    total          = models.DecimalField(max_digits=10, decimal_places=2)
    urgent         = models.BooleanField(default=False)
    delivery_date  = models.CharField(max_length=20, blank=True)
    urgent_charge  = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delivery_zone       = models.CharField(max_length=20, default='inside')
    delivery_charge     = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    promo_code     = models.CharField(max_length=50, blank=True, default='')
    promo_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_screenshot  = models.ImageField(upload_to='payments/screenshots/', null=True, blank=True)
    upi_id          = models.CharField(max_length=100, blank=True, default='')
    transaction_id  = models.CharField(max_length=50, blank=True, default='')
    payment_status    = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notification_seen = models.BooleanField(default=False)
    created_at        = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.order_id

    @property
    def can_cancel(self):
        return self.status in ('pending', 'confirmed') and not hasattr(self, '_cancel_request_cache')


class CancelRequest(models.Model):
    CANCEL_STATUS = [
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    order          = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='cancel_request')
    reason         = models.TextField()
    status         = models.CharField(max_length=20, choices=CANCEL_STATUS, default='pending')
    admin_response = models.TextField(blank=True, default='')
    requested_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at    = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Cancel — {self.order.order_id} [{self.status}]"


class ContactMessage(models.Model):
    name       = models.CharField(max_length=100)
    email      = models.EmailField()
    subject    = models.CharField(max_length=200, blank=True, default='')
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}: {self.subject or 'No Subject'}"


class PopupOffer(models.Model):
    title         = models.CharField(max_length=100, blank=True, default='')
    subtitle      = models.CharField(max_length=200, blank=True, default='')
    badge_text    = models.CharField(max_length=50, blank=True, default='')
    discount_text = models.CharField(max_length=50, blank=True, default='')
    image         = models.ImageField(upload_to='popup_offers/', null=True, blank=True)
    product       = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='popup_offers')
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Popup Offer'


class Wishlist(models.Model):
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product  = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} → {self.product.name}"
