from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.home, name='home'),
    path("addorder/", views.add_order),
    path("orders/<pk>/", views.get_orders),
    path('create/', views.create_payment, name='create_payment'),
    path('invoice/<pk>/', views.track_invoice, name='track_payment'),
    path('receive/', views.receive_payment, name='receive_payment'),
    path("users/", views.get_users, name="users"),
    path("users/banned/", views.get_banned_users),
    path("user/<pk>/", views.get_user, name="user"),
    path("createuser/", views.create_user),
    path("products/", views.get_products),
    path("product/<pk>/", views.get_product),
    path("invoices/", views.get_invoices),
    path("invoice/<pk>/", views.get_invoice),
    path("ban/", views.ban_user),
    path("unban/", views.unban_user),
    path("status/", views.change_status),
    path("balance/", views.update_user_balance),
    path("deleteproduct/", views.delete_product),
    path("createproduct/", views.create_product),
    path("updateproduct/", views.update_product),
    path("createcoupon/", views.create_coupon),
    path("coupons/", views.get_coupons),
    path("coupons/delete/", views.delete_coupon),
    path("createvipcoupon/", views.create_vipcoupon),
    path("vipcoupons/", views.getvip_coupons),
    path("vipcoupons/delete/", views.deletevip_coupon),
    path("usersdump/", views.users_dump),
    path("coupon/<code>/", views.get_coupon),
    path("createorder/", views.create_order),
    path("markcoupon/", views.mark_coupon),
    path("pendingorders/<user_id>/", views.pending_users_orders),
    path("settledorders/<user_id>/", views.settled_users_orders),
    path("approveorders/", views.approve_order),
    path("transactiontoday/", views.transactions_today),
    path("transactionweekly/", views.transactions_weekly),
    path("transactionmonthly/", views.transactions_monthly),
    path("transactionall/", views.transactions_all)
]

