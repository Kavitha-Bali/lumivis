from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0014_popupoffer_fields_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='upi_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='transaction_id',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('pending',  'Pending Verification'),
                    ('verified', 'Payment Verified'),
                    ('rejected', 'Payment Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
