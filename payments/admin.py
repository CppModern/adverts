from django.contrib import admin
from .models import *
# Register your models here.
admin.site.register(Invoice)
admin.site.register(Product)
admin.site.register(Coupon)
admin.site.register(VIPCoupon)
admin.site.register(Order)
admin.site.register(Transaction)
