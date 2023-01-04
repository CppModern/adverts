import datetime
from datetime import timedelta
import os
from pathlib import Path
import django.http as http
import telegram
from django.http.response import JsonResponse
from django.shortcuts import render, reverse
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from accounts.models import MyUser
from django.core.serializers import serialize
from .models import Invoice
from .models import Coupon
from .models import Product
from .models import Transaction
from .models import Order
from .models import VIPCoupon
from .models import ServiceOrder
import requests
import uuid
import toml

BASE_DIR = Path(__file__).resolve().parent.parent


def home(request):
    products = Product.objects.all()
    return render(request, "product.html", context={"products": products})


@csrf_exempt
def add_order(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    qty = request.POST.get("qty")
    name = request.POST.get("name")
    category = request.POST.get("category")
    link = request.POST.get("link")
    service = request.POST.get("service")
    user = request.POST.get("user_id")
    source = request.POST.get("source")
    order = ServiceOrder.objects.create(
        service=service, name=name, category=category, qty=qty, user=user, link=link, source=source
    )
    order.save()
    return JsonResponse({"order": order.pk})


def get_orders(request: http.HttpRequest, pk):
    if request.method != "GET":
        return JsonResponse({"error": "method not allowed"})
    orders: list[ServiceOrder] = ServiceOrder.objects.filter(user=pk)
    info = []
    for order in orders:
        data = {}
        attrs = ["name", "service", "link", "qty", "order_id"]
        for attr in attrs:
            data[attr] = getattr(order, attr)
        info.append(data)
    return JsonResponse({"orders": info})


def get_order_status(request: http.HttpRequest, user, pk):
    if request.method != "GET":
        return JsonResponse({"error": "method not allowed"})
    try:
        order: ServiceOrder = ServiceOrder.objects.get(user=user, order_id=pk)
        source = order.source
        if source == 1:
            """smmstone"""

        elif source == 2:
            """crescitaly"""
    except Exception:
        pass
# ------------------- Coupon Views ---------------------------


@csrf_exempt
def create_coupon(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    code = request.POST.get("code")
    discount = request.POST.get("discount")
    coupon = Coupon.objects.get_or_create(code=code)[0]
    coupon.discount = discount
    coupon.save()
    msg = "Coupon created"
    return JsonResponse({"msg": msg})


@csrf_exempt
def create_vipcoupon(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    code = request.POST.get("code")
    discount = request.POST.get("discount")
    coupon = VIPCoupon.objects.get_or_create(code=code)[0]
    coupon.discount = discount
    coupon.save()
    msg = "Coupon created"
    return JsonResponse({"msg": msg})


@csrf_exempt
def delete_coupon(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    code = request.POST.get("code")
    coupon = Coupon.objects.get(code=code)
    coupon.delete()
    msg = "Coupon deleted"
    return JsonResponse({"msg": msg})


@csrf_exempt
def deletevip_coupon(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    code = request.POST.get("code")
    coupon = Coupon.objects.get(code=code)
    coupon.delete()
    msg = "Coupon deleted"
    return JsonResponse({"msg": msg})


def get_coupons(request: http.HttpRequest):
    res = serialize("json", Coupon.objects.filter(used=False), fields=["code", 'discount'])
    return JsonResponse({"coupons": res})


def get_coupon(request: http.HttpRequest, code):
    try:
        coupon = Coupon.objects.get(code=code)
    except Exception as e:
        res = []
    else:
        res = {"code": coupon.code, "discount": coupon.discount, "used": coupon.used}
    return JsonResponse({"coupon": res})


def getvip_coupons(request: http.HttpRequest):
    res = serialize("json", [VIPCoupon.objects.order_by("date_added")[-1]], fields=["code", 'discount'])
    return JsonResponse({"coupons": res})


@csrf_exempt
def mark_coupon(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    code = request.POST.get("code")
    coupon: Coupon = Coupon.objects.get(code=code)
    coupon.count += 1
    coupon.save()
    return JsonResponse({"count": coupon.count})


# ----------------------- User Views -----------------------------
def get_users(request: http.HttpRequest):
    data = []
    users = MyUser.objects.filter(banned=False)
    fields = ["telegram_id", "balance", "status", "fname", "username"]
    for user in users:
        info = {}
        for field in fields:
            info[field] = getattr(user, field)
        data.append(info)
    return JsonResponse({"users": data})


def get_banned_users(request: http.HttpRequest):
    users = serialize(
        "json", MyUser.objects.filter(banned=True),
        fields=["telegram_id", "balance", "status", "fname"]
    )
    return JsonResponse({"users": users})


def get_user(request: http.HttpRequest, pk):
    try:
        user: MyUser = MyUser.objects.get(pk=pk)
    except Exception:
        return JsonResponse({"user": {}})
    balance = user.balance
    banned = user.banned
    fname = user.fname
    username = user.username
    discount = user.discount
    status = "VIP" if user.status == "vip" else "Regular"
    telegram_id = user.telegram_id
    trans_count = user.transactions.count()
    trans_paid = user.transactions.filter(settled=True).count()
    trans_unpaid = user.transactions.filter(settled=False).count()
    orders_count = user.orders.count()
    orders_approved = user.orders.filter(settled=True).count()
    orders_unapproved = user.orders.filter(settled=False).count()
    info = {
        "fname": fname, "username": username, "discount": discount, "banned": banned,
        "balance": balance, "status": status, "telegram_id": telegram_id, "trans_count": trans_count,
        "trans_unpaid": trans_unpaid, "trans_paid": trans_paid, "orders_count": orders_count,
        "orders_approved": orders_approved, "orders_unapproved": orders_unapproved
    }
    return JsonResponse({"user": info})


@csrf_exempt
def create_user(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    telegram_id = request.POST.get("user_id")
    fname = request.POST.get("fname")
    username = request.POST.get("username")
    try:
        user = MyUser.objects.get(
            telegram_id=telegram_id
        )
    except Exception as e:
        user = MyUser.objects.create_user(
            telegram_id=telegram_id, password="default", fname=fname, username=username
        )
        user.save()
    return get_user(request, user.telegram_id)


@csrf_exempt
def ban_user(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    pk = request.POST.get("user_id")
    lang = request.POST.get("loc", "")
    user = MyUser.objects.get(telegram_id=pk)
    user.banned = True
    user.save()
    msg = "user banned" if lang == "en" else "user banned"
    return JsonResponse({"msg": msg})


@csrf_exempt
def unban_user(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    pk = request.POST.get("user_id")
    lang = request.POST.get("loc", "")
    user = MyUser.objects.get(telegram_id=pk)
    user.banned = False
    user.save()
    msg = "user unbanned" if lang == "en" else "User unbanned"
    return JsonResponse({"msg": msg})


@csrf_exempt
def change_status(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    pk = request.POST.get("user_id")
    user = MyUser.objects.get(telegram_id=pk)
    user.status = "regular" if user.status == "vip" else "vip"
    user.save()
    msg = "user status changed"
    return JsonResponse({"msg": msg})


def users_dump(request: http.HttpRequest):
    users = MyUser.objects.filter(banned=False)
    data = []
    for user in users:
        user: MyUser
        info = {"username": user.username, "id": user.telegram_id}
        data.append(info)
    return JsonResponse({"users": data})


@csrf_exempt
def update_user_balance(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    pk = request.POST.get("user_id")
    amount = request.POST.get("amount")
    deduct = request.POST.get("charge")
    user = MyUser.objects.get(telegram_id=pk)
    if deduct:
        user.balance -= float(amount)
    else:
        user.balance += float(amount)
    user.save()
    return JsonResponse({"msg": "OK"})


# ------------------------ Product Views --------------------------

def get_products(request: http.HttpRequest):
    products = serialize("json", Product.objects.all())
    return JsonResponse({"products": products})


@csrf_exempt
def create_product(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    price = request.POST.get("price")
    description = request.POST.get("desc")
    title = request.POST.get("name")
    volume = request.POST.get("volume")
    try:
        prod = Product.objects.create(price=price, description=description, title=title, volume=volume)
    except Exception as e:
        print(e)
        return HttpResponse("fatal")
    else:
        prod.save()
        msg = "Product created"
    return JsonResponse({"msg": msg})


@csrf_exempt
def delete_product(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    product_id = request.POST.get("product_id")
    product = Product.objects.get(product_id=product_id)
    product.delete()
    msg = "product deleted"
    return JsonResponse({"msg": msg})


@csrf_exempt
def update_product(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    price = request.POST.get("price")
    description = request.POST.get("desc")
    title = request.POST.get("name")
    volume = request.POST.get("volume")
    product_id = request.POST.get("product_id")
    product = Product.objects.get(product_id=product_id)
    product.price = price
    product.description = description
    product.title = title
    product.volume = volume
    product.save()
    return JsonResponse({"msg": "product updated"})


def get_product(request: http.HttpRequest, pk):
    product = serialize("json", Product.objects.filter(pk=pk))
    return JsonResponse({"product": product})


# ------------------ Transaction views ------------------------------

def get_invoices(request: http.HttpRequest):
    products = serialize("json", Transaction.objects.all())
    return JsonResponse({"invoices": products})


def get_invoice(request: http.HttpRequest, pk):
    product = serialize("json", Transaction.objects.filter(pk=pk))
    return JsonResponse({"invoice": product})


def get_trans_info(trans: list[Transaction]):
    data = []
    for tran in trans:
        info = dict()
        info["status"] = Transaction.STATUS_CHOICES[tran.status + 1][1]
        info["date"] = tran.created_at.strftime("%d/%m/%Y")
        info["paid"] = tran.received or 0
        info["user"] = str(tran.created_by)
        data.append(info)
    return data


def transactions_today(request: http.HttpRequest):
    transactions: list[Transaction] = Transaction.objects.filter(
        created_at__gte=datetime.date.today()
    )
    data = get_trans_info(transactions)
    return JsonResponse({"transactions": data})


def transactions_weekly(request: http.HttpRequest):
    transactions: list[Transaction] = Transaction.objects.filter(
        created_at__gte=datetime.datetime.now() - timedelta(days=7)
    )
    data = get_trans_info(transactions)
    return JsonResponse({"transactions": data})


def transactions_monthly(request: http.HttpRequest):
    transactions: list[Transaction] = Transaction.objects.filter(
        created_at__gte=datetime.datetime.now() - timedelta(days=30)
    )
    data = get_trans_info(transactions)
    return JsonResponse({"transactions": data})


def transactions_all(request: http.HttpRequest):
    transactions = Transaction.objects.all()
    data = get_trans_info(transactions)
    return JsonResponse({"transactions": data})


def exchanged_rate(amount):
    url = "https://www.blockonomics.co/api/price?currency=USD"
    r = requests.get(url)
    response = r.json()
    rate = response["price"]
    return (float(amount) / rate), rate


def track_invoice(request, pk):
    try:
        invoice = Transaction.objects.get(order_id=pk)
    except Exception as e:
        data = {}
        return JsonResponse({"data": data})
    data = {
        "order_id": invoice.order_id,
        "bits": invoice.btcvalue,
        "value": invoice.amount,
        "addr": invoice.address,
        "status": Invoice.STATUS_CHOICES[invoice.status + 1][1],
        "invoice_status": invoice.status,
    }
    if invoice.received:
        data["paid"] = invoice.received
    else:
        data["paid"] = 0
    # return render(request, "invoice.html", context=data)
    return JsonResponse({"data": data})


@csrf_exempt
def create_payment(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    user_id = request.POST.get("user_id")
    amount = request.POST.get("amount")
    user = MyUser.objects.get(telegram_id=user_id)
    url = "https://www.blockonomics.co/api/new_address?reset=1"
    headers = {"Authorization": "Bearer " + settings.API_KEY}
    r = requests.post(url, headers=headers)
    if r.status_code == 200:
        address = r.json()["address"]
        bits, btcrate = exchanged_rate(amount)
        order_id = uuid.uuid1()
        invoice = Transaction.objects.create(
            order_id=order_id, address=address, btcvalue=bits,
            created_by=user, rate=btcrate * 1e-8, amount=amount
        )
        data = {
            "link": reverse("payments:track_payment", kwargs={"pk": invoice.id}),
            "address": address,
            "btc_price": bits,
            "order_id": order_id,
            "msg": False
        }
    else:
        data = {
            "msg": r.reason
        }
    return JsonResponse({"data": data})


def receive_payment(request: http.HttpRequest):
    if request.method != "GET":
        return
    txid = request.GET.get("txid")
    value = request.GET.get("value")
    status = request.GET.get("status")
    addr = request.GET.get("addr")

    invoice = Transaction.objects.get(address=addr)
    invoice.status = int(status)
    if int(status) == 2:
        invoice.received = (invoice.rate * int(value))
        cpath = BASE_DIR / "tg_bot/config.toml"
        with open(cpath, encoding="utf8") as file:
            cfg = toml.load(file)
            token = cfg["Telegram"]["token"]
        bot = telegram.Bot(token=token)
        bot.get_me()
        msg = f"Your payment of {invoice.received} shekels has been confirmed and your funds will be credited shortly"
        user_id = int(invoice.created_by.telegram_id)
        bot.send_message(user_id, msg)
        invoice.created_by.balance += invoice.received
        invoice.created_by.save()
    invoice.txid = txid
    invoice.save()
    return HttpResponse(200)


# ------------------ Order Views ---------------------------
@csrf_exempt
def create_order(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    product_id = request.POST.get("product_id")
    coupon_code = request.POST.get("coupon")
    qty = request.POST.get("qty")
    user_id = request.POST.get("user")
    if coupon_code:
        coupon: Coupon = Coupon.objects.get(code=coupon_code)
    user = MyUser.objects.get(telegram_id=user_id)
    product: Product = Product.objects.get(product_id=product_id)
    if coupon_code:
        order: Order = Order.objects.create(coupon=coupon, product=product, quantity=qty, user=user)
    else:
        order: Order = Order.objects.create(product=product, quantity=qty, user=user)
    order.save()
    # TODO send notification to admins
    return JsonResponse({"msg": "order created"})


def pending_users_orders(request: http.HttpRequest, user_id):
    orders: list[Order] = Order.objects.filter(user=user_id).filter(settled=False).select_related()
    if not orders:
        return JsonResponse({"orders": []})
    orderlist = []
    for order in orders:
        info = dict()
        info["date"] = order.date.strftime("%d/%m/%Y")
        info["product"] = order.product.title
        info["paid"] = order.actual_price
        info["volume"] = order.product.volume
        orderlist.append(info)
    return JsonResponse({"orders": orderlist})


def settled_users_orders(request: http.HttpRequest, user_id):
    orders: list[Order] = Order.objects.filter(user=user_id).filter(settled=True).select_related()
    if not orders:
        return JsonResponse({"orders": []})
    orderlist = []
    for order in orders:
        info = dict()
        info["date"] = order.date.strftime("%d/%m/%Y")
        info["product"] = order.product.title
        info["paid"] = order.actual_price
        info["volume"] = order.product.volume
        orderlist.append(info)
    return JsonResponse({"orders": orderlist})


def approve_order(request: http.HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"})
    order_id = request.POST.get("order_id")
    order: Order = Order.objects.get(order_id=order_id)
    order.settled = True
    order.save()
    return JsonResponse({"msg": "OK"})
