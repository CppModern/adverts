import sys
import logging
import queue as queuem
import threading
import traceback
import json
import requests
import nuconfig
import telegram
import _signals
import localization
import adminmenu as menu
import usermenu as user_menu

from utils import (
    wait_for_photo, wait_for_regex,
    wait_for_inlinekeyboard_callback,
    receive_next_update, wait_for_specific_message,
    graceful_stop, buildmenubutton
)

log = logging.getLogger(__name__)
CancelSignal = _signals.CancelSignal
StopSignal = _signals.StopSignal


class User:
    def __init__(self, kwargs: dict, user: telegram.User):
        self.admin = kwargs.get("is_admin")
        self.balance = kwargs.get("balance")
        self.telegram_id = kwargs.get("telegram_id")
        self.first_name = user.first_name
        self.username = user.username
        self.id = user.id

    def __str__(self):
        return f"{self.first_name} [{self.id}]"

    def mention(self):
        if self.username:
            return f"@{self.username}"
        return self.id


class Worker(threading.Thread):
    CancelSignal = _signals.CancelSignal
    StopSignal = _signals.StopSignal
    wait_for_specific_message = wait_for_specific_message
    wait_for_inlinekeyboard_callback = wait_for_inlinekeyboard_callback
    receive_next_update = receive_next_update
    wait_for_photo = wait_for_photo
    wait_for_regex = wait_for_regex
    graceful_stop = graceful_stop

    user_service_menu = user_menu.servicemenu
    user_funds_menu = user_menu.fundsmenu
    user_order_menu = user_menu.ordermenu
    # user_profile_menu = user_menu.profile_menu

    def __init__(
        self,
        bot,
        chat: telegram.Chat,
        telegram_user: telegram.User,
        cfg: nuconfig.NuConfig,
        *args,
        **kwargs,
    ):
        # Initialize the thread
        super().__init__(name=f"Worker {chat.id}", *args, **kwargs)
        # Store the bot, chat info and config inside the class
        self.bot: telegram.Bot = bot
        self.chat: telegram.Chat = chat
        self.todelete = []
        self.telegram_user: telegram.User = telegram_user
        self.cfg = cfg
        # The sending pipe is stored in the Worker class,
        # allowing the forwarding of messages to the chat process
        self.queue = queuem.Queue()
        # The current active invoice payload; reject all invoices
        # with a different payload
        self.invoice_payload = None
        self.__create_localization()
        self.cancel_marked = telegram.InlineKeyboardMarkup(
            [[telegram.InlineKeyboardButton(self.loc.get("menu_cancel"), callback_data="cmd_cancel")]])
        self.cancel_list = [telegram.InlineKeyboardButton(self.loc.get("menu_cancel"), callback_data="cmd_cancel")]
        # The price class of this worker.

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.chat.id}>"

    def run(self):
        """The conversation code."""
        self.create_user()
        log.debug("Starting conversation")
        # Capture exceptions that occour during the conversation
        # noinspection PyBroadException
        try:
            # Welcome the user to the bot
            if self.cfg["Appearance"]["display_welcome_message"] == "yes":
                self.bot.send_message(
                    self.chat.id, self.loc.get("conversation_after_start")
                )
                self.cfg["Appearance"]["display_welcome_message"] = "no"

            # If the user is not an admin, send him to the user menu
            """if not self.user.admin:
                self.__user_menu()
            # If the user is an admin, send him to the admin menu
            else:
                self.__admin_menu()"""
            self.user_menu()
        except Exception as e:
            # Try to notify the user of the exception
            # noinspection PyBroadException
            try:
                self.bot.send_message(
                    self.chat.id, self.loc.get("fatal_conversation_exception")
                )
            except Exception as ne:
                log.error(
                    f"Failed to notify the user of a conversation exception: {ne}"
                )
            log.error(f"Exception in {self}: {e}")
            traceback.print_exception(*sys.exc_info())

    def is_ready(self):
        # Change this if more parameters are added!
        return self.loc is not None

    def stop(self, reason: str = ""):
        """Gracefully stop the worker process"""
        # Send a stop message to the thread
        self.queue.put(StopSignal(reason))
        # Wait for the thread to stop
        self.join()

    """def update_user(self):
        user_data = json.loads(
            requests.get(self.cfg["API"]["base"].format(f"payment/user/{self.user.id}")).json()["user"]
        )
        self.user = User(user_data[0], user=self.telegram_user)
        return self.user"""

    def __create_localization(self):
        self.loc = localization.Localization("en")

    def user_menu(self, selection: telegram.CallbackQuery = None):
        data = {
            "service": self.loc.get("serviceButton"),
            "funds": self.loc.get("fundsButton"),
            "order": self.loc.get("orderButton"),
            "contact": self.loc.get("contactButtont"),
        }
        keyboard = buildmenubutton(data, cancellable=False)
        if selection:
            selection.edit_message_text(
                self.loc.get("user_welcome").format(self.telegram_user.first_name),
                reply_markup=telegram.InlineKeyboardMarkup(keyboard)
            )
        else:
            self.bot.send_message(
                self.chat.id,
                self.loc.get("user_welcome").format(self.telegram_user.first_name),
                reply_markup=telegram.InlineKeyboardMarkup(keyboard)
            )
        selection = self.wait_for_inlinekeyboard_callback()
        if selection.data == "service":
            self.user_service_menu(selection=selection)
        elif selection.data == "funds":
            self.user_funds_menu(selection=selection)
        elif selection.data == "profile":
            self.user_profile_menu(selection=selection)
        elif selection.data == "order":
            self.user_order_menu(selection=selection, adding=False)

    def admin_menu(self, button: telegram.CallbackQuery = None):
        keyboard = [
            [
                telegram.InlineKeyboardButton(
                    self.loc.get("product"),
                    callback_data="product"
                ),
                telegram.InlineKeyboardButton(
                    self.loc.get("payments"),
                    callback_data="payments"
                )
            ],
            [
                telegram.InlineKeyboardButton(
                    self.loc.get("add_credit"),
                    callback_data="credit"
                ),
                telegram.InlineKeyboardButton(self.loc.get("user_button"), callback_data="users")
            ],
            [
                telegram.InlineKeyboardButton(
                    self.loc.get("promo_button"), callback_data="promo"
                ),
                telegram.InlineKeyboardButton(
                    self.loc.get("vippromo_button"), callback_data="vippromo"
                )
            ],
            [
                telegram.InlineKeyboardButton(
                    self.loc.get("csv_menu"), callback_data="csv"
                ),
                telegram.InlineKeyboardButton(
                    self.loc.get("customer_mode"), callback_data="user_mode"
                )
            ],
            [
                telegram.InlineKeyboardButton(
                    self.loc.get("language_button"), callback_data="lang"
                )
            ]

        ]
        if not button:
            self.bot.send_message(
                self.chat.id,
                text=self.loc.get("conversation_open_admin_menu"),
                reply_markup=telegram.InlineKeyboardMarkup(
                    keyboard
                ),
            )
        else:
            button.edit_message_text(
                self.loc.get("conversation_open_admin_menu"),
                reply_markup=telegram.InlineKeyboardMarkup(
                    keyboard
                ),
            )
        selection = self.wait_for_inlinekeyboard_callback()
        if selection.data == "product":
            self.admin_product_menu(selection=selection)
        elif selection.data == "credit":
            self.admin_credit_menu(selection=selection)
        elif selection.data == "users":
            self.admin_user_menu(selection=selection)
        elif selection.data == "promo":
            self.admin_promo_menu(selection)
        elif selection.data == "vippromo":
            self.admin_vippromo_menu(selection)
        elif selection.data == "csv":
            self.admin_csv_menu(selection=selection)
        elif selection.data == "lang":
            self.switch_context(selection=selection)
        elif selection.data == "user_mode":
            self.user_menu(selection=selection)
        elif selection.data == "payments":
            self.admin_transaction_menu(selection=selection)

    def switch_context(self, selection: telegram.CallbackQuery = None, toadmin=True):
        if self.telegram_user.language_code != "en":
            selection.edit_message_text(
                self.loc.get("translation_fail")
            )
            if toadmin:
                return self.admin_menu()

    def get_orders(self):
        url = self.cfg["API"]["base"].format(f"payment/orders/{self.telegram_user.id}/")
        orders = requests.get(url).json()["orders"]
        return orders

    def list_products(self):
        url = self.cfg["API"]["base"].format("payment/products/")
        prods = json.loads(requests.get(url).json()["products"])
        return prods

    def get_users(self):
        url = self.cfg["API"]["base"].format("payment/users/")
        users = requests.get(url).json()["users"]
        return users

    def addorder(self, details):
        url = self.cfg["API"]["base"].format("payment/addorder/")
        requests.post(url, details)

    def getorders(self, user_id):
        url = self.cfg["API"]["base"].format(f"payment/orders/{user_id}")
        res = requests.get(url).json()
        return res["orders"]

    def user_dump(self):
        url = self.cfg["API"]["base"].format("payment/usersdump/")
        res = requests.get(url).json()["users"]
        return res

    def create_or_update_product(self, data, update=False):
        if update:
            url = self.cfg["API"]["base"].format("payment/updateproduct/")
        else:
            url = self.cfg["API"]["base"].format("payment/createproduct/")
        res = requests.post(url, data=data).json()
        return res

    def delete_product(self, product):
        url = self.cfg["API"]["base"].format("payment/deleteproduct/")
        res = requests.post(url, data={"product_id": product})
        return res.json()

    def get_banned_users(self):
        url = self.cfg["API"]["base"].format("payment/users/banned/")
        users = json.loads(requests.get(url).json()["users"])
        data = []
        for user in users:
            data.append(user["fields"])
        return data

    def create_user(self):
        url = self.cfg["API"]["base"].format("payment/createuser/")
        data = {
            "user_id": self.telegram_user.id,
            "fname": self.telegram_user.first_name,
            "username": self.telegram_user.username or ""
        }
        requests.post(url, data=data)

    def ban(self, user):
        user = str(user)
        data = {"user_id": user, "loc": self.telegram_user.language_code}
        url = self.cfg["API"]["base"].format(f"payment/ban/")
        res = requests.post(url, data=data).json()
        return res

    def unban(self, user):
        user = str(user)
        data = {"user_id": user, "loc": self.telegram_user.language_code}
        url = self.cfg["API"]["base"].format(f"payment/unban/")
        res = requests.post(url, data=data).json()
        return res

    def update_balace(self, user, amout, charge=False):
        user = str(user)
        if charge:
            data = {"user_id": user, "amount": amout, "charge": True}
        else:
            data = {"user_id": user, "amount": amout}
        url = self.cfg["API"]["base"].format(f"payment/balance/")
        res = requests.post(url, data=data).json()
        return res

    def change_status(self, user):
        user = str(user)
        data = {"user_id": user, "loc": self.telegram_user.language_code}
        url = self.cfg["API"]["base"].format(f"payment/status/")
        res = requests.post(url, data=data).json()
        return res

    def get_user(self, user_id):
        url = self.cfg["API"]["base"].format(f"payment/user/{user_id}/")
        user = requests.get(url).json()["user"]
        return user

    def create_coupon(self, code, discount):
        url = self.cfg["API"]["base"].format(f"payment/createcoupon/")
        data = {"code": code, "discount": discount}
        res = requests.post(url, data=data).json()
        return res

    def create_order(self, user, product_id, qty, coupon=None):
        data = {"user": user, "product_id": product_id, "qty": qty, "coupon": coupon}
        url = self.cfg["API"]["base"].format(f"payment/createorder/")
        res = requests.post(url, data=data).json()
        return res

    def get_coupons(self):
        url = self.cfg["API"]["base"].format("payment/coupons/")
        res = json.loads(requests.get(url).json()["coupons"])
        return res

    def mark_coupon(self, code):
        data = {"code": code}
        url = self.cfg["API"]["base"].format("payment/markcoupon/")
        res = requests.post(url, data=data).json()
        return res

    def get_coupon(self, code):
        url = self.cfg["API"]["base"].format(f"payment/coupon/{code}")
        res = requests.get(url).json()["coupon"]
        return res

    def delete_coupon(self, code):
        url = self.cfg["API"]["base"].format(f"payment/coupons/delete/")
        data = {"code": code}
        res = requests.post(url, data=data).json()
        return res

    def createvip_coupon(self, code, discount):
        url = self.cfg["API"]["base"].format(f"payment/createvipcoupon/")
        data = {"code": code, "discount": discount}
        res = requests.post(url, data=data).json()
        return res

    def getvip_coupons(self):
        url = self.cfg["API"]["base"].format(f"payment/vipcoupons/")
        res = json.loads(requests.get(url).json()["coupons"])
        return res

    def deletevip_coupon(self, code):
        url = self.cfg["API"]["base"].format(f"payment/vipcoupons/delete/")
        data = {"code": code}
        res = requests.post(url, data=data).json()
        return res

    def pending_user_orders(self, user):
        url = self.cfg["API"]["base"].format(f"payment/pendingorders/{user}")
        res = requests.get(url)
        return res.json()["orders"]

    def settled_user_orders(self, user):
        url = self.cfg["API"]["base"].format(f"payment/settledorders/{user}")
        res = requests.get(url)
        return res.json()["orders"]

    def create_payment(self, user, amount):
        data = {"user_id": user, "amount": amount}
        url = self.cfg["API"]["base"].format(f"payment/create/")
        res = requests.post(url, data=data).json()
        return res

    def track_payment(self, order_id):
        url = self.cfg["API"]["base"].format(f"payment/invoice/{order_id}")
        res = requests.get(url).json()
        return res["data"]

    def transaction_times(self, day="today"):
        url = self.cfg["API"]["base"].format(f"payment/transaction{day}/")
        res = requests.get(url).json()
        return res["transactions"]

