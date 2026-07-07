from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0015_order_payment_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='notification_seen',
            field=models.BooleanField(default=False),
        ),
    ]
