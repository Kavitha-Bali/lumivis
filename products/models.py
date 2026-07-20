import io
import os

from PIL import Image

from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import User


def _is_fresh_upload(field_file):
    """
    True for a just-picked file straight off the upload form — not one already in storage.
    Checked via Django's own `_committed` flag (set False only on a freshly-assigned,
    not-yet-saved file). Must NOT touch `field_file.file` here: for an already-committed
    field that property lazily downloads the file from storage (Azure, in this project) —
    which means every edit to a product with an existing image would re-download it, and
    fail the whole save if that download ever errors.
    """
    return bool(field_file) and not field_file._committed


def _compress_image(field_file, max_dimension, quality=82):
    """Downscale + re-encode as JPEG so product photos don't slow the homepage down."""
    image = Image.open(field_file)
    if image.mode not in ('RGB', 'L'):
        # Covers RGBA/P/LA (needs flattening) and CMYK (Pillow's CMYK JPEGs render
        # with wrong colors in browsers, which expect YCbCr) — always normalize to RGB.
        image = image.convert('RGB')
    image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=quality, optimize=True)
    buffer.seek(0)
    base_name = os.path.splitext(os.path.basename(field_file.name))[0]
    return ContentFile(buffer.read(), name=f'{base_name}.jpg')


def _compress_field(field_file, max_dimension, quality=82):
    """Replace a freshly-uploaded ImageField's content with a compressed version, in place."""
    if _is_fresh_upload(field_file):
        compressed = _compress_image(field_file, max_dimension, quality)
        field_file.save(compressed.name, compressed, save=False)


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

    def save(self, *args, **kwargs):
        # Auto-generate a thumbnail from the main image if the admin didn't upload
        # one — otherwise listing pages (homepage, All Products, related products)
        # fall back to serving the full-size photo for any product without an
        # explicit thumbnail, which is exactly the slow-loading grid this avoids.
        if _is_fresh_upload(self.image) and not self.thumbnail:
            self.image.seek(0)
            thumb = _compress_image(self.image, max_dimension=500)
            self.thumbnail.save(thumb.name, thumb, save=False)
            self.image.seek(0)
        _compress_field(self.image, max_dimension=1600)
        _compress_field(self.thumbnail, max_dimension=500)
        _compress_field(self.cover_image, max_dimension=1920)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery_images')
    image      = models.ImageField(upload_to='products/gallery/')
    order      = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        _compress_field(self.image, max_dimension=1600)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} — gallery image {self.pk}"


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
    refunded       = models.BooleanField(default=False)
    refunded_at    = models.DateTimeField(null=True, blank=True)

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

    def save(self, *args, **kwargs):
        _compress_field(self.image, max_dimension=1000)
        super().save(*args, **kwargs)

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
