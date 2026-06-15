from django.db import models

# Create your models here.

class Product(models.Model):
    name = models.CharField(max_length=100)
    product_id = models.CharField(max_length=50, unique=True)
    product_type = models.CharField(max_length=50)
    product_size = models.CharField(max_length=50)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name
    

class transctions(models.Model):
    transaction_id = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.product.name}"
    

class promocode(models.Model):
    promo_code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    expiry_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.promo_code  
    







        
