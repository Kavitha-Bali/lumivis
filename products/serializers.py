from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Product, transctions, promocode, ratings, Wishlist


# ── Helpers ───────────────────────────────────────────────────────────────────

def _abs_image(obj, request):
    if not obj.image:
        return None
    url = obj.image.url
    return request.build_absolute_uri(url) if request else url


# ── User ──────────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model        = User
        fields       = ['id', 'username', 'email', 'is_staff', 'date_joined']
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirm password')

    class Meta:
        model  = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2    = serializers.CharField(write_only=True, label='Confirm new password')

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['email', 'first_name', 'last_name']


# ── Product ───────────────────────────────────────────────────────────────────

class ProductSerializer(serializers.ModelSerializer):
    image_url     = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id', 'name', 'product_id', 'product_type', 'product_size',
            'description', 'price',
            'image', 'image_url',
            'thumbnail', 'thumbnail_url',
        ]
        extra_kwargs = {
            'image':     {'write_only': True, 'required': False},
            'thumbnail': {'write_only': True, 'required': False},
        }

    def get_image_url(self, obj):
        return _abs_image(obj, self.context.get('request'))

    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return None
        url = obj.thumbnail.url
        req = self.context.get('request')
        return req.build_absolute_uri(url) if req else url

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Price must be greater than zero.')
        return value

    def validate_product_id(self, value):
        qs = Product.objects.filter(product_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A product with this SKU already exists.')
        return value


class ProductMiniSerializer(serializers.ModelSerializer):
    """Lightweight serializer used inside nested responses."""
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = ['id', 'name', 'product_type', 'price', 'image_url']

    def get_image_url(self, obj):
        return _abs_image(obj, self.context.get('request'))


# ── Transaction / Order ───────────────────────────────────────────────────────

class TransactionSerializer(serializers.ModelSerializer):
    product = ProductMiniSerializer(read_only=True)
    user    = UserSerializer(read_only=True)

    class Meta:
        model  = transctions
        fields = [
            'id', 'transaction_id', 'user', 'product',
            'quantity', 'total_price', 'transaction_date', 'status',
        ]
        read_only_fields = ['transaction_id', 'transaction_date']


# ── Cart ──────────────────────────────────────────────────────────────────────

class CartItemSerializer(serializers.Serializer):
    product  = ProductMiniSerializer()
    quantity = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)


# ── Checkout ──────────────────────────────────────────────────────────────────

class CheckoutItemSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity   = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    """
    Optional explicit items list.
    If omitted the server falls back to the session cart.
    """
    items = CheckoutItemSerializer(many=True, required=False, default=list)


# ── Promo Code ────────────────────────────────────────────────────────────────

class PromocodeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = promocode
        fields = '__all__'

    def validate_discount_percentage(self, value):
        if not (0 < value <= 100):
            raise serializers.ValidationError('Discount must be between 0 and 100.')
        return value


class PromocodeValidateSerializer(serializers.Serializer):
    promo_code = serializers.CharField(max_length=50)


# ── Ratings ───────────────────────────────────────────────────────────────────

class RatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model  = ratings
        fields = ['id', 'user', 'product', 'rating', 'review', 'created_at']
        read_only_fields = ['created_at', 'user']
        extra_kwargs = {'product': {'write_only': True}}


# ── Wishlist ──────────────────────────────────────────────────────────────────

class WishlistSerializer(serializers.ModelSerializer):
    product = ProductMiniSerializer(read_only=True)

    class Meta:
        model  = Wishlist
        fields = ['id', 'product', 'added_at']
        read_only_fields = ['added_at']
