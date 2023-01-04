import datetime
import uuid
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model

UserModel = get_user_model()


def product_image_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/actual/<filename>
    return "actual/{0}".format(filename)


def product_thumb_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/thumb/<filename>
    return "thumb/{0}".format(filename)


def gen_id():
    return uuid.uuid4().int


def gen_id2():
    return uuid.uuid4().hex


class Product(models.Model):
    product_id = models.CharField(max_length=50, default=gen_id)
    title = models.CharField(max_length=50)
    description = models.TextField()
    price = models.FloatField()
    volume = models.IntegerField(default=1, blank=True)
    minimumQty = models.IntegerField(default=1)

    def __str__(self):
        return self.title


class Coupon(models.Model):
    code = models.CharField(max_length=100)
    discount = models.FloatField()
    used = models.BooleanField(default=False)
    count = models.IntegerField(default=0)

    def __str__(self):
        return self.code


class VIPCoupon(models.Model):
    code = models.CharField(max_length=100)
    discount = models.FloatField()
    used = models.BooleanField(default=False)
    date_added = models.DateField(auto_now_add=True)

    class Meta:
        ordering = "date_added",

    def __str__(self):
        return self.code


class Order(models.Model):
    order_id = models.CharField(max_length=100, default=gen_id)
    user = models.ForeignKey(UserModel, on_delete=models.SET_NULL, blank=True, null=True, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="products")
    coupon = models.ForeignKey(Coupon, blank=True, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(default=1)  # quantity for the product
    date = models.DateField(default=timezone.now)
    settled = models.BooleanField(default=False)

    @property
    def actual_price(self):
        self.product: Product
        self.coupon: Coupon
        if self.coupon:
            right = self.quantity * self.product.price
            left = self.quantity * self.product.price * self.coupon.discount
            return right - left
        return self.quantity * self.product.price


class Invoice(models.Model):
    STATUS_CHOICES = (
        (-1, "Not Started"),
        (0, "Unconfirmed"),
        (1, "Partially Confirmed"),
        (2, "Confirmed"),
    )
    created_by = models.ForeignKey(UserModel, on_delete=models.CASCADE, null=True)
    product = models.ForeignKey("Product", on_delete=models.CASCADE)
    status = models.IntegerField(choices=STATUS_CHOICES, default=-1)
    order_id = models.CharField(max_length=250)
    address = models.CharField(max_length=250, blank=True, null=True)
    btcvalue = models.IntegerField(blank=True, null=True)
    received = models.IntegerField(blank=True, null=True)
    txid = models.CharField(max_length=250, blank=True, null=True)
    rbf = models.IntegerField(blank=True, null=True)
    created_at = models.DateField(auto_now=True)
    rate = models.FloatField(default=0, blank=True)
    settled = models.BooleanField(default=False)

    def __str__(self):
        return self.address


class Transaction(models.Model):
    STATUS_CHOICES = (
        (-1, "Not Started"),
        (0, "Unconfirmed"),
        (1, "Partially Confirmed"),
        (2, "Confirmed"),
    )
    amount = models.FloatField()
    created_by = models.ForeignKey(UserModel, on_delete=models.CASCADE, null=True, related_name="transactions")
    status = models.IntegerField(choices=STATUS_CHOICES, default=-1)
    order_id = models.CharField(max_length=250)
    address = models.CharField(max_length=250, blank=True, null=True)
    btcvalue = models.FloatField(blank=True, null=True)
    received = models.FloatField(blank=True, null=True)
    txid = models.CharField(max_length=250, blank=True, null=True)
    rbf = models.IntegerField(blank=True, null=True)
    created_at = models.DateField(default=datetime.date.today)
    rate = models.FloatField(default=0, blank=True)
    settled = models.BooleanField(default=False)


class ServiceOrder(models.Model):
    order_id = models.CharField(max_length=200, default=gen_id2)
    service = models.CharField(max_length=10)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=200)
    qty = models.IntegerField(default=0)
    user = models.IntegerField()
    date_added = models.DateTimeField(default=datetime.date.today)
    link = models.CharField(max_length=200)
    source = models.IntegerField(default=0)
