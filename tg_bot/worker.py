import os
import sys
import datetime
import logging
import queue as queuem
import re
import threading
import traceback
import uuid
from html import escape
from typing import *
import json
import requests
import nuconfig
import telegram
import translations.en as en
import translations.heb as heb
log = logging.getLogger(__name__)


class User:
    def __init__(self, kwargs: dict):
        print(kwargs)
        self.admin = kwargs.get("is_admin")
        self.balance = kwargs.get("balance")
        self.telegram_id = kwargs.get("telegram_id")


class StopSignal:
    """A data class that should be sent to the worker when
    the conversation has to be stopped abnormally."""

    def __init__(self, reason: str = ""):
        self.reason = reason


class CancelSignal:
    """An empty class that is added to the queue whenever the
    user presses a cancel inline button."""

    pass


class Worker(threading.Thread):
    """A worker for a single conversation. A new one is created
    every time the /start command is sent."""

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
        self.bot = bot
        self.chat: telegram.Chat = chat
        user_data = json.loads(requests.get(cfg["API"]["base"].format(f"payment/user/{telegram_user.id}")).json()["user"])
        print(telegram_user.id)
        if data := user_data[0]:
            print(type(data))
            self.user = User(data)
        else:
            # TODO what happens if the user is not reg?
            self.user = None
        self.telegram_user: telegram.User = telegram_user
        self.cfg = cfg
        self.loc = None

        # The sending pipe is stored in the Worker class,
        # allowing the forwarding of messages to the chat process
        self.queue = queuem.Queue()
        # The current active invoice payload; reject all invoices
        # with a different payload
        self.invoice_payload = None
        # The price class of this worker.

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.chat.id}>"


    def run(self):
        """The conversation code."""
        log.debug("Starting conversation")
        # Create the localization object
        self.__create_localization()
        # Capture exceptions that occour during the conversation
        # noinspection PyBroadException
        try:
            # Welcome the user to the bot
            if self.cfg["Appearance"]["display_welcome_message"] == "yes":
                self.bot.send_message(
                    self.chat.id, self.loc.get("conversation_after_start")
                )
            # If the user is not an admin, send him to the user menu
            """if not self.user.admin:
                self.__user_menu()
            # If the user is an admin, send him to the admin menu
            else:
                self.__admin_menu()"""
            self.__admin_menu()
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

    def update_user(self):
        """Update the user data."""
        log.debug("Fetching updated user data from the database")
        self.user = (
            self.session.query(db.User)
            .filter(db.User.user_id == self.chat.id)
            .one_or_none()
        )
        return self.user

    # noinspection PyUnboundLocalVariable
    def __receive_next_update(self) -> telegram.Update:
        """Get the next update from the queue.
        If no update is found, block the process until one is received.
        If a stop signal is sent, try to gracefully stop the thread."""
        # Pop data from the queue
        try:
            data = self.queue.get(timeout=self.cfg["Telegram"]["conversation_timeout"])
        except queuem.Empty:
            # If the conversation times out, gracefully stop the thread
            self.__graceful_stop(StopSignal("timeout"))
        # Check if the data is a stop signal instance
        if isinstance(data, StopSignal):
            # Gracefully stop the process
            self.__graceful_stop(data)
        # Return the received update
        return data

    def __wait_for_specific_message(
        self, items: List[str], cancellable: bool = False
    ) -> Union[str, CancelSignal]:
        """Continue getting updates until until one of the strings contained in the list is received as a message."""
        log.debug("Waiting for a specific message...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update contains a message
            if update.message is None:
                continue
            # Ensure the message contains text
            if update.message.text is None:
                continue
            # Check if the message is contained in the list
            if update.message.text not in items:
                continue
            # Return the message text
            return update.message.text

    def __wait_for_regex(
        self, regex: str, cancellable: bool = False
    ) -> Union[str, CancelSignal]:
        """Continue getting updates until the regex finds a match in a message, then return the first capture group."""
        log.debug("Waiting for a regex...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update contains a message
            if update.message is None:
                continue
            # Ensure the message contains text
            if update.message.text is None:
                continue
            # Try to match the regex with the received message
            match = re.search(regex, update.message.text, re.DOTALL)
            # Ensure there is a match
            if match is None:
                continue
            # Return the first capture group
            return match.group(1)

    def __wait_for_precheckoutquery(
        self, cancellable: bool = False
    ) -> Union[telegram.PreCheckoutQuery, CancelSignal]:
        """Continue getting updates until a precheckoutquery is received.
        The payload is checked by the core before forwarding the message."""
        log.debug("Waiting for a PreCheckoutQuery...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update contains a precheckoutquery
            if update.pre_checkout_query is None:
                continue
            # Return the precheckoutquery
            return update.pre_checkout_query

    def __wait_for_successfulpayment(
        self, cancellable: bool = False
    ) -> Union[telegram.SuccessfulPayment, CancelSignal]:
        """Continue getting updates until a successfulpayment is received."""
        log.debug("Waiting for a SuccessfulPayment...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update contains a message
            if update.message is None:
                continue
            # Ensure the message is a successfulpayment
            if update.message.successful_payment is None:
                continue
            # Return the successfulpayment
            return update.message.successful_payment

    def __send_btc_payment_info(self, address, amount):
        # Send a message containing the btc pay info
        self.bot.send_message_markdown(
            self.chat.id,
            "To pay, send this amount:\n`"
            + str(amount)
            + "`\nto this bitcoin address:\n`"
            + address
            + "`",
        )

    def __wait_for_photo(
        self, cancellable: bool = False
    ) -> Union[List[telegram.PhotoSize], CancelSignal]:
        """Continue getting updates until a photo is received, then return it."""
        log.debug("Waiting for a photo...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update contains a message
            if update.message is None:
                continue
            # Ensure the message contains a photo
            if update.message.photo is None:
                continue
            # Return the photo array
            return update.message.photo

    def __wait_for_inlinekeyboard_callback(
        self, cancellable: bool = False
    ) -> Union[telegram.CallbackQuery, CancelSignal]:
        """Continue getting updates until an inline keyboard callback is received, then return it."""
        log.debug("Waiting for a CallbackQuery...")
        while True:
            # Get the next update
            update = self.__receive_next_update()
            # If a CancelSignal is received...
            if isinstance(update, CancelSignal):
                # And the wait is cancellable...
                if cancellable:
                    # Return the CancelSignal
                    return update
                else:
                    # Ignore the signal
                    continue
            # Ensure the update is a CallbackQuery
            if update.callback_query is None:
                continue
            # Answer the callbackquery
            self.bot.answer_callback_query(update.callback_query.id)
            # Return the callbackquery
            return update.callback_query

    def __user_select(self) -> Union[User, CancelSignal]:
        """Select an user from the ones in the database."""
        log.debug("Waiting for a user selection...")
        # Find all the users in the database
        users = self.session.query(db.User).order_by(db.User.user_id).all()
        # Create a list containing all the keyboard button strings
        keyboard_buttons = [[self.loc.get("menu_cancel")]]
        # Add to the list all the users
        for user in users:
            keyboard_buttons.append([user.identifiable_str()])
        # Create the keyboard
        keyboard = telegram.ReplyKeyboardMarkup(
            keyboard_buttons, one_time_keyboard=True
        )
        # Keep asking until a result is returned
        while True:
            # Send the keyboard
            self.bot.send_message(
                self.chat.id,
                self.loc.get("conversation_admin_select_user"),
                reply_markup=keyboard,
            )
            # Wait for a reply
            reply = self.__wait_for_regex("user_([0-9]+)", cancellable=True)
            # Propagate CancelSignals
            if isinstance(reply, CancelSignal):
                return reply
            # Find the user in the database
            user = (
                self.session.query(db.User).filter_by(user_id=int(reply)).one_or_none()
            )
            # Ensure the user exists
            if not user:
                self.bot.send_message(
                    self.chat.id, self.loc.get("error_user_does_not_exist")
                )
                continue
            return user

    def __user_menu(self):
        """Function called from the run method when the user is not an administrator.
        Normal bot actions should be placed here."""
        log.debug("Displaying __user_menu")
        # Loop used to returning to the menu after executing a command
        while True:
            # Create a keyboard with the user main menu
            keyboard = [
                [
                    telegram.KeyboardButton(self.loc.get("menu_order")),
                    telegram.KeyboardButton(self.loc.get("menu_order_status")),
                ],
                [
                    telegram.KeyboardButton(self.loc.get("menu_add_credit")),
                    telegram.KeyboardButton(self.loc.get("menu_search_products")),
                ],
                [
                    telegram.KeyboardButton(self.loc.get("menu_help")),
                    telegram.KeyboardButton(self.loc.get("menu_language")),
                ]
            ]
            # Send the previously created keyboard to the user
            #  (ensuring it can be clicked only 1 time)
            news = (
                self.session.query(db.News)
                .filter(db.News.expiry_date > datetime.datetime.now())
                .all()
            )
            if news:
                info = "NEW INFO:\n"
                for n in news:
                    info += n.info + "\n\n"
                self.bot.send_message(self.chat.id, info)

            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "conversation_open_user_menu",
                    credit=self.Price(self.user.credit)
                ),
                reply_markup=telegram.ReplyKeyboardMarkup(
                    keyboard, one_time_keyboard=True
                ),
            )
            # Wait for a reply from the user
            selection = self.__wait_for_specific_message(
                [
                    self.loc.get("menu_order"),
                    self.loc.get("menu_order_status"),
                    self.loc.get("menu_search_products"),
                    self.loc.get("menu_add_credit"),
                    self.loc.get("menu_language"),
                    self.loc.get("menu_help"),
                ]
            )
            # After the user reply, update the user data
            self.update_user()
            # If the user has selected the Order option...
            if selection == self.loc.get("menu_order"):
                # Open the order menu
                self.__order_menu()
            # if the user is searching products
            elif selection == self.loc.get("menu_search_products"):
                self.__search_menu()
            # If the user has selected the Order Status option...
            elif selection == self.loc.get("menu_order_status"):
                # Display the order(s) status
                self.__order_status()
            # If the user has selected the Add Credit option...
            elif selection == self.loc.get("menu_add_credit"):
                # Display the add credit menu
                self.__add_credit_menu()
            # If the user has selected the Language option...
            elif selection == self.loc.get("menu_language"):
                # Display the language menu
                self.__language_menu()
            # If the user has selected the Bot Info option...
            elif selection == self.loc.get("menu_bot_info"):
                # Display information about the bot
                self.__bot_info()
            # If the user has selected the Help option...
            elif selection == self.loc.get("menu_help"):
                # Go to the Help menu
                self.__help_menu()

    def __search_menu(self):
        """User  menu to search products"""
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_search_menu"))
        name = self.__wait_for_regex("(.*)")
        products = self.session.query(db.Product).filter(
            db.Product.name.like(f"{name}%")).all()
        if products:
            self.__order_menu(products=products, categorise=False)
        else:
            self.bot.send_message(
                self.chat.id,
                self.loc.get("search_404"))

    def __order_menu(self, products=None, categorise=True):
        """User menu to order products from the shop."""
        log.debug("Displaying __order_menu")
        if not products:
            # Get the products list from the db
            products: list[db.Product] = (
                self.session.query(db.Product).filter_by(deleted=False).all()
            )
            categories_names = list(set([product.category for product in products]))
            categories_menu = [
                [telegram.KeyboardButton(i)] for i in categories_names]
            categories_names.append(self.loc.get("menu_cancel"))
            categories_menu.append(
                [telegram.KeyboardButton(self.loc.get("menu_cancel"))])
            self.bot.send_message(
                self.chat.id,
                self.loc.get("menu_product_categories"),
                reply_markup=telegram.ReplyKeyboardMarkup(
                    categories_menu, one_time_keyboard=True
                ),
            )
            selection = self.__wait_for_specific_message(
                categories_names, cancellable=True)
            if isinstance(selection, CancelSignal):
                return
        # Create a dict to be used as 'cart'
        # The key is the message id of the product list
        cart: dict[list[db.Product, int]] = {}
        # Initialize the products list
        for product in products:
            # If the product is not for sale, don't display it
            if product.price is None:
                continue
            if categorise and product.category != selection:
                continue
            # Send the message without the keyboard to get the message id
            message = product.send_as_message(w=self, chat_id=self.chat.id)
            # Add the product to the cart
            cart[message["result"]["message_id"]] = [product, 0]
            # Create the inline keyboard to add the product to the cart
            inline_keyboard = telegram.InlineKeyboardMarkup(
                [
                    [
                        telegram.InlineKeyboardButton(
                            self.loc.get("menu_add_to_cart"),
                            callback_data="cart_add"
                        )
                    ]
                ]
            )
            # Edit the sent message and add the inline keyboard
            if product.image is None:
                self.bot.edit_message_text(
                    chat_id=self.chat.id,
                    message_id=message["result"]["message_id"],
                    text=product.text(w=self),
                    reply_markup=inline_keyboard,
                )
            else:
                self.bot.edit_message_caption(
                    chat_id=self.chat.id,
                    message_id=message["result"]["message_id"],
                    caption=product.text(w=self),
                    reply_markup=inline_keyboard,
                )
        # Create the keyboard with the cancel button
        inline_keyboard = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_cancel"),
                        callback_data="cart_cancel"
                    )
                ]
            ]
        )
        # Send a message containing the button to cancel or pay
        final_msg = self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_cart_actions"),
            reply_markup=inline_keyboard,
        )
        # Wait for user input
        while True:
            callback = self.__wait_for_inlinekeyboard_callback()
            # React to the user input
            # If the cancel button has been pressed...
            if callback.data == "cart_cancel":
                # Stop waiting for user input and go back to the previous menu
                return
            # If a Add to Cart button has been pressed...
            elif callback.data == "cart_add":
                # Get the selected product, ensuring it exists
                p = cart.get(callback.message.message_id)
                if p is None:
                    continue
                product = p[0]
                # Add 1 copy to the cart
                if cart[callback.message.message_id][1] > product.quantity:
                    return
                else:
                    cart[callback.message.message_id][1] += 1
                # Create the product inline keyboard
                product_inline_keyboard = telegram.InlineKeyboardMarkup(
                    [
                        [
                            telegram.InlineKeyboardButton(
                                self.loc.get("menu_add_to_cart"),
                                callback_data="cart_add",
                            ),
                            telegram.InlineKeyboardButton(
                                self.loc.get("menu_remove_from_cart"),
                                callback_data="cart_remove",
                            ),
                        ]
                    ]
                )
                # Create the final inline keyboard
                final_inline_keyboard = telegram.InlineKeyboardMarkup(
                    [
                        [
                            telegram.InlineKeyboardButton(
                                self.loc.get("menu_cancel"), callback_data="cart_cancel"
                            )
                        ],
                        [
                            telegram.InlineKeyboardButton(
                                self.loc.get("menu_done"), callback_data="cart_done"
                            )
                        ],
                    ]
                )
                # Edit both the product and the final message
                if product.image is None:
                    self.bot.edit_message_text(
                        chat_id=self.chat.id,
                        message_id=callback.message.message_id,
                        text=product.text(
                            w=self, cart_qty=cart[callback.message.message_id][1]
                        ),
                        reply_markup=product_inline_keyboard,
                    )
                else:
                    self.bot.edit_message_caption(
                        chat_id=self.chat.id,
                        message_id=callback.message.message_id,
                        caption=product.text(
                            w=self, cart_qty=cart[callback.message.message_id][1]
                        ),
                        reply_markup=product_inline_keyboard,
                    )

                self.bot.edit_message_text(
                    chat_id=self.chat.id,
                    message_id=final_msg.message_id,
                    text=self.loc.get(
                        "conversation_confirm_cart",
                        product_list=self.__get_cart_summary(cart),
                        total_cost=str(self.__get_cart_value(cart)),
                    ),
                    reply_markup=final_inline_keyboard,
                )
            # If the Remove from cart button has been pressed...
            elif callback.data == "cart_remove":
                # Get the selected product, ensuring it exists
                p = cart.get(callback.message.message_id)
                if p is None:
                    continue
                product = p[0]
                # Remove 1 copy from the cart
                if cart[callback.message.message_id][1] > 0:
                    cart[callback.message.message_id][1] -= 1
                else:
                    continue
                # Create the product inline keyboard
                product_inline_list = [
                    [
                        telegram.InlineKeyboardButton(
                            self.loc.get("menu_add_to_cart"), callback_data="cart_add"
                        )
                    ]
                ]
                if cart[callback.message.message_id][1] > 0:
                    product_inline_list[0].append(
                        telegram.InlineKeyboardButton(
                            self.loc.get("menu_remove_from_cart"),
                            callback_data="cart_remove",
                        )
                    )
                product_inline_keyboard = telegram.InlineKeyboardMarkup(
                    product_inline_list
                )
                # Create the final inline keyboard
                final_inline_list = [
                    [
                        telegram.InlineKeyboardButton(
                            self.loc.get("menu_cancel"), callback_data="cart_cancel"
                        )
                    ]
                ]
                for product_id in cart:
                    if cart[product_id][1] > 0:
                        final_inline_list.append(
                            [
                                telegram.InlineKeyboardButton(
                                    self.loc.get("menu_done"), callback_data="cart_done"
                                )
                            ]
                        )
                        break
                final_inline_keyboard = telegram.InlineKeyboardMarkup(final_inline_list)
                # Edit the product message
                if product.image is None:
                    self.bot.edit_message_text(
                        chat_id=self.chat.id,
                        message_id=callback.message.message_id,
                        text=product.text(
                            w=self, cart_qty=cart[callback.message.message_id][1]
                        ),
                        reply_markup=product_inline_keyboard,
                    )
                else:
                    self.bot.edit_message_caption(
                        chat_id=self.chat.id,
                        message_id=callback.message.message_id,
                        caption=product.text(
                            w=self, cart_qty=cart[callback.message.message_id][1]
                        ),
                        reply_markup=product_inline_keyboard,
                    )

                self.bot.edit_message_text(
                    chat_id=self.chat.id,
                    message_id=final_msg.message_id,
                    text=self.loc.get(
                        "conversation_confirm_cart",
                        product_list=self.__get_cart_summary(cart),
                        total_cost=str(self.__get_cart_value(cart)),
                    ),
                    reply_markup=final_inline_keyboard,
                )
            # If the done button has been pressed...
            elif callback.data == "cart_done":
                # End the loop
                break
        # Create an inline keyboard with a single skip button
        cancel = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_skip"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        # Ask if the user wants to add notes to the order
        self.bot.send_message(
            self.chat.id, self.loc.get("ask_order_notes"), reply_markup=cancel
        )
        # Wait for user input
        notes = self.__wait_for_regex(r"(.*)", cancellable=True)
        # Create a new Order
        order = db.Order(
            user=self.user,
            creation_date=datetime.datetime.now(),
            notes=notes if not isinstance(notes, CancelSignal) else "",
        )
        # Add the record to the session and get an ID
        self.session.add(order)
        # For each product added to the cart, create a new OrderItem
        orders = []
        for product in cart:
            # Create {quantity} new OrderItems
            for i in range(0, cart[product][1]):
                order_item = db.OrderItem(product=cart[product][0], order=order)
                self.session.add(order_item)
                orders.append(order_item)
        # Ensure the user has enough credit to make the purchase
        credit_required = self.__get_cart_value(cart) - self.user.credit
        # Notify user in case of insufficient credit
        if credit_required > 0:
            self.bot.send_message(self.chat.id, self.loc.get("error_not_enough_credit"))
            # Suggest payment for missing credit value if configuration allows refill
            if (
                self.cfg["Payments"]["CreditCard"]["credit_card_token"] != ""
                and self.cfg["Appearance"]["refill_on_checkout"]
                and self.Price(self.cfg["Payments"]["CreditCard"]["min_amount"])
                <= credit_required
                <= self.Price(self.cfg["Payments"]["CreditCard"]["max_amount"])
            ):
                self.__make_payment(self.Price(credit_required))
        # If afer requested payment credit is still insufficient (either payment failure or cancel)
        if self.user.credit < self.__get_cart_value(cart):
            # Rollback all the changes
            self.session.rollback()
        else:
            for o in orders:
                o: db.OrderItem
                o.product.deleted = True
            self.session.commit()
            # User has credit and valid order, perform transaction now
            self.__order_transaction(
                order=order, value=-int(self.__get_cart_value(cart))
            )

    def __get_cart_value(self, cart):
        # Calculate total items value in cart
        value = self.Price(0)
        for product in cart:
            value += cart[product][0].price * cart[product][1]
        return value

    def __get_cart_summary(self, cart):
        # Create the cart summary
        product_list = ""
        for product_id in cart:
            if cart[product_id][1] > 0:
                product_list += (
                    cart[product_id][0].text(
                        w=self, style="short", cart_qty=cart[product_id][1]
                    )
                    + "\n"
                )
        return product_list

    def __order_transaction(self, order, value):
        # Create a new transaction and add it to the session
        transaction = db.Transaction(user=self.user, value=value, order=order)
        self.session.add(transaction)
        # Commit all the changes
        self.session.commit()
        # Update the user's credit
        self.user.recalculate_credit()
        # Commit all the changes
        self.session.commit()
        # Notify admins about new transation
        self.__order_notify_admins(order=order)

    def __order_notify_admins(self, order):
        # Notify the user of the order result
        item = (
            self.session.query(db.OrderItem)
            .filter(db.OrderItem.order_id == order.order_id)
            .one_or_none()
        )
        notes = item.product.notes
        self.bot.send_message(
            self.chat.id,
            self.loc.get(
                "success_order_created",
                order=order.text(w=self, user=True) + f"Seller Notes: {notes}",
            ),
        )
        # Notify the admins (in Live Orders mode) of the new order
        admins = self.session.query(db.Admin).filter_by(live_mode=True).all()
        # Create the order keyboard
        order_keyboard = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_complete"), callback_data="order_complete"
                    )
                ],
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_refund"), callback_data="order_refund"
                    )
                ],
            ]
        )
        # Notify them of the new placed order
        for admin in admins:
            self.bot.send_message(
                admin.user_id,
                self.loc.get("notification_order_placed", order=order.text(w=self)),
                reply_markup=order_keyboard,
            )

    def __order_status(self):
        """Display the status of the sent orders."""
        log.debug("Displaying __order_status")
        # Find the latest orders
        orders = (
            self.session.query(db.Order)
            .filter(db.Order.user == self.user)
            .order_by(db.Order.creation_date.desc())
            .limit(20)
            .all()
        )
        # Ensure there is at least one order to display

        if len(orders) == 0:
            self.bot.send_message(self.chat.id, self.loc.get("error_no_orders"))
        # Display the order status to the user
        for order in orders:
            order: db.Order
            orderitem = (
                self.session.query(db.OrderItem)
                .filter(db.OrderItem.order_id == order.order_id)
                .one_or_none()
            )
            notes = orderitem.product.notes
            self.bot.send_message(
                self.chat.id, order.text(w=self, user=True) + f"\nSeller Notes: {notes}"
            )
        # TODO: maybe add a page displayer instead of showing the latest 5 orders

    def __add_credit_menu(self):
        """Add more credit to the account."""
        log.debug("Displaying __add_credit_menu")
        # Create a payment methods keyboard
        keyboard = list()
        # Add the supported payment methods to the keyboard
        # Cash
        # keyboard.append([telegram.KeyboardButton(self.loc.get("menu_cash"))])
        # Telegram Payments
        """if self.cfg["Payments"]["CreditCard"]["credit_card_token"] != "":
            keyboard.append([telegram.KeyboardButton(self.loc.get("menu_credit_card"))])"""
        # Bitcoin Payments
        if self.cfg["Bitcoin"]["api_key"] != "":
            keyboard.append([telegram.KeyboardButton("???? Bitcoin")])
        # Keyboard: go back to the previous menu
        keyboard.append([telegram.KeyboardButton(self.loc.get("menu_cancel"))])
        # Send the keyboard to the user
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_payment_method"),
            reply_markup=telegram.ReplyKeyboardMarkup(keyboard, one_time_keyboard=True),
        )
        # Wait for a reply from the user
        selection = self.__wait_for_specific_message(
            [
                self.loc.get("menu_cash"),
                self.loc.get("menu_credit_card"),
                "???? Bitcoin",
                self.loc.get("menu_cancel"),
            ],
            cancellable=True,
        )
        # If the user has selected the Cash option...
        if selection == self.loc.get("menu_cash"):
            # Go to the pay with cash function
            self.bot.send_message(
                self.chat.id,
                self.loc.get("payment_cash", user_cash_id=self.user.identifiable_str()),
            )
        # If the user has selected the Credit Card option...
        elif selection == self.loc.get("menu_credit_card"):
            # Go to the pay with credit card function
            self.__add_credit_cc()
        # If the user has selected the Bitcoin option...
        elif selection == "???? Bitcoin":
            # Go to the pay with bitcoin function
            self.__add_credit_btc()
        # If the user has selected the Cancel option...
        elif isinstance(selection, CancelSignal):
            # Send him back to the previous menu
            return

    def __add_credit_cc(self):
        """Add money to the wallet through a credit card payment."""
        log.debug("Displaying __add_credit_cc")
        # Create a keyboard to be sent later
        presets = self.cfg["Payments"]["CreditCard"]["payment_presets"]
        keyboard = [
            [telegram.KeyboardButton(str(self.Price(preset)))] for preset in presets
        ]
        keyboard.append([telegram.KeyboardButton(self.loc.get("menu_cancel"))])
        # Boolean variable to check if the user has cancelled the action
        cancelled = False
        # Loop used to continue asking if there's an error during the input
        while not cancelled:
            # Send the message and the keyboard
            self.bot.send_message(
                self.chat.id,
                self.loc.get("payment_cc_amount"),
                reply_markup=telegram.ReplyKeyboardMarkup(
                    keyboard, one_time_keyboard=True
                ),
            )
            # Wait until a valid amount is sent
            selection = self.__wait_for_regex(
                r"([0-9]+(?:[.,][0-9]+)?|" + self.loc.get("menu_cancel") + r")",
                cancellable=True,
            )
            # If the user cancelled the action
            if isinstance(selection, CancelSignal):
                # Exit the loop
                cancelled = True
                continue
            # Convert the amount to an integer
            value = self.Price(selection)
            # Ensure the amount is within the range
            if value > self.Price(self.cfg["Payments"]["CreditCard"]["max_amount"]):
                self.bot.send_message(
                    self.chat.id,
                    self.loc.get(
                        "error_payment_amount_over_max",
                        max_amount=self.Price(self.cfg["CreditCard"]["max_amount"]),
                    ),
                )
                continue
            elif value < self.Price(self.cfg["Payments"]["CreditCard"]["min_amount"]):
                self.bot.send_message(
                    self.chat.id,
                    self.loc.get(
                        "error_payment_amount_under_min",
                        min_amount=self.Price(self.cfg["CreditCard"]["min_amount"]),
                    ),
                )
                continue
            break
        # If the user cancelled the action...
        else:
            # Exit the function
            return
        # Issue the payment invoice
        self.__make_payment(amount=value)

    def __make_payment(self, amount):
        # Set the invoice active invoice payload
        self.invoice_payload = str(uuid.uuid4())
        # Create the price array
        prices = [
            telegram.LabeledPrice(
                label=self.loc.get("payment_invoice_label"), amount=int(amount)
            )
        ]
        # If the user has to pay a fee when using the credit card, add it to the prices list
        fee = int(self.__get_total_fee(amount))
        if fee > 0:
            prices.append(
                telegram.LabeledPrice(
                    label=self.loc.get("payment_invoice_fee_label"), amount=fee
                )
            )
        # Create the invoice keyboard
        inline_keyboard = telegram.InlineKeyboardMarkup(
            [
                [telegram.InlineKeyboardButton(self.loc.get("menu_pay"), pay=True)],
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_cancel"), callback_data="cmd_cancel"
                    )
                ],
            ]
        )
        # The amount is valid, send the invoice
        self.bot.send_invoice(
            self.chat.id,
            title=self.loc.get("payment_invoice_title"),
            description=self.loc.get("payment_invoice_description", amount=str(amount)),
            payload=self.invoice_payload,
            provider_token=self.cfg["Payments"]["CreditCard"]["credit_card_token"],
            start_parameter="tempdeeplink",
            currency=self.cfg["Payments"]["currency"],
            prices=prices,
            need_name=self.cfg["Payments"]["CreditCard"]["name_required"],
            need_email=self.cfg["Payments"]["CreditCard"]["email_required"],
            need_phone_number=self.cfg["Payments"]["CreditCard"]["phone_required"],
            reply_markup=inline_keyboard,
            max_tip_amount=self.cfg["Payments"]["CreditCard"]["max_tip_amount"],
            suggested_tip_amounts=self.cfg["Payments"]["CreditCard"]["tip_presets"],
        )
        # Wait for the precheckout query
        precheckoutquery = self.__wait_for_precheckoutquery(cancellable=True)
        # Check if the user has cancelled the invoice
        if isinstance(precheckoutquery, CancelSignal):
            # Exit the function
            return
        # Accept the checkout
        self.bot.answer_pre_checkout_query(precheckoutquery.id, ok=True)
        # Wait for the payment
        successfulpayment = self.__wait_for_successfulpayment(cancellable=False)
        # Create a new database transaction
        transaction = db.Transaction(
            user=self.user,
            value=int(amount),
            provider="Credit Card",
            telegram_charge_id=successfulpayment.telegram_payment_charge_id,
            provider_charge_id=successfulpayment.provider_payment_charge_id,
        )

        if successfulpayment.order_info is not None:
            transaction.payment_name = successfulpayment.order_info.name
            transaction.payment_email = successfulpayment.order_info.email
            transaction.payment_phone = successfulpayment.order_info.phone_number
        # Update the user's credit
        self.user.recalculate_credit()
        # Commit all the changes
        self.session.commit()


    def __get_total_fee(self, amount):
        # Calculate a fee for the required amount
        fee_percentage = self.cfg["Payments"]["CreditCard"]["fee_percentage"] / 100
        fee_fixed = self.cfg["Payments"]["CreditCard"]["fee_fixed"]
        total_fee = amount * fee_percentage + fee_fixed
        if total_fee > 0:
            return total_fee
        # Set the fee to 0 to ensure no accidental discounts are applied
        return 0

    def __bot_info(self):
        """Send information about the bot."""
        log.debug("Displaying __bot_info")
        self.bot.send_message(self.chat.id, self.loc.get("bot_info"))

    def __admin_menu(self):
        """Function called from the run method when the user is an administrator.
        Administrative bot actions should be placed here."""
        log.debug("Displaying __admin_menu")
        # Loop used to return to the menu after executing a command
        while True:
            # Create a keyboard with the admin main menu based on the admin
            # permissions specified in the db
            keyboard = []
            keyboard.append(
                [
                    self.loc.get("menu_products"),
                    #self.loc.get("menu_edit_credit")
                ]
            )
            """keyboard.append(
                [
                    self.loc.get("menu_orders"),
                    self.loc.get("menu_csv")
                ]
            )
            keyboard.append(
                [
                    self.loc.get("menu_transactions"),
                    self.loc.get("menu_user_mode")]
            )"""

            # Send the previously created keyboard to the user
            # (ensuring it can be clicked only 1 time)
            self.bot.send_message(
                self.chat.id,
                self.loc.get("conversation_open_admin_menu"),
                reply_markup=telegram.ReplyKeyboardMarkup(
                    keyboard, resize_keyboard=True, one_time_keyboard=True
                ),
            )
            # Wait for a reply from the user
            selection = self.__wait_for_specific_message(
                [
                    self.loc.get("menu_products"),
                ]
            )
            # If the user has selected the Products option...
            if selection == self.loc.get("menu_products"):
                # Open the products menu
                self.__products_menu()
            # If the user has selected the Orders option...
            elif selection == self.loc.get("menu_orders"):
                # Open the orders menu
                self.__orders_menu()
            # If the user has selected the Transactions option...
            elif selection == self.loc.get("menu_edit_credit"):
                # Open the edit credit menu
                self.__create_transaction()
            # If the user has selected the User mode option...
            elif selection == self.loc.get("menu_user_mode"):
                # Tell the user how to go back to admin menu
                self.bot.send_message(
                    self.chat.id,
                    self.loc.get("conversation_switch_to_user_mode")
                )
                # Start the bot in user mode
                self.__user_menu()
            # If the user has selected the Add Admin option...
            elif selection == self.loc.get("menu_edit_admins"):
                # Open the edit admin menu
                self.__add_admin()
            # If the user has selected the Transactions option...
            elif selection == self.loc.get("menu_transactions"):
                # Open the transaction pages
                self.__transaction_pages()
            # If the user has selected the .csv option...
            elif selection == self.loc.get("menu_csv"):
                # Generate the .csv file
                self.__transactions_file()
            elif selection == self.loc.get("menu_news"):
                self.__news()

    def __news(self):
        cancel = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_skip"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        self.bot.send_message(
            self.chat.id,
            self.loc.get("news_info_prompt"),
            reply_markup=cancel)
        info = self.__wait_for_regex("(.*)", cancellable=True)
        if isinstance(info, CancelSignal):
            return
        else:
            news = db.News(
                info=info,
                expiry_date=datetime.datetime.now() + datetime.timedelta(
                    hours=12))
            self.session.add(news)
            self.session.commit()
            self.bot.send_message(self.chat.id, self.loc.get("news_added"))

    def __products_menu(self):
        """Display the admin menu to select a product to edit."""
        log.debug("Displaying __products_menu")
        # Get the products list from the db
        products = self.session.query(db.Product).filter_by(deleted=False).all()
        # Create a list of product names
        product_names = [product.name for product in products]
        # Insert at the start of the list the add product option, the remove
        # product option and the Cancel option
        product_names.insert(0, self.loc.get("menu_cancel"))
        product_names.insert(1, self.loc.get("menu_add_product"))
        product_names.insert(2, self.loc.get("menu_delete_product"))
        # Create a keyboard using the product names
        keyboard = [
            [telegram.KeyboardButton(
                product_name)] for product_name in product_names
        ]
        # Send the previously created keyboard to the user
        # (ensuring it can be clicked only 1 time)
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_admin_select_product"),
            reply_markup=telegram.ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True),
        )
        # Wait for a reply from the user
        selection = self.__wait_for_specific_message(
            product_names, cancellable=True)
        # If the user has selected the Cancel option...
        if isinstance(selection, CancelSignal):
            # Exit the menu
            return
        # If the user has selected the Add Product option...
        elif selection == self.loc.get("menu_add_product"):
            # Open the add product menu
            self.__edit_product_menu()
        # If the user has selected the Remove Product option...
        elif selection == self.loc.get("menu_delete_product"):
            # Open the delete product menu
            self.__delete_product_menu()
        # If the user has selected a product
        else:
            # Find the selected product
            product = (
                self.session.query(db.Product)
                .filter_by(name=selection, deleted=False)
                .one()
            )
            # Open the edit menu for that specific product
            self.__edit_product_menu(product=product)

    def __edit_product_menu(self, product=None):
        """Add a product to the database or edit an existing one."""
        log.debug("Displaying __edit_product_menu")
        # Create an inline keyboard with a single skip button
        cancel = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_skip"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        # Ask for the product name until a valid product name is specified
        while True:
            # Ask the question to the user
            self.bot.send_message(
                self.chat.id, self.loc.get("ask_product_name"))
            # Display the current name if you're editing an existing product
            if product:
                self.bot.send_message(
                    self.chat.id,
                    self.loc.get(
                        "edit_current_value",
                        value=escape(product.name)),
                    reply_markup=cancel,
                )
            # Wait for an answer
            name = self.__wait_for_regex(r"(.*)", cancellable=bool(product))
            # Ensure a product with that name doesn't already exist
            if (product and isinstance(name, CancelSignal)) or\
                self.session.query(db.Product).filter_by(
                    name=name, deleted=False).one_or_none() in [None, product]:
                # Exit the loop
                break
            self.bot.send_message(
                self.chat.id, self.loc.get("error_duplicate_name"))
        # Ask for the product description
        self.bot.send_message(
            self.chat.id, self.loc.get("ask_product_description"))
        # Display the current description if you're editing an existing product
        if product:
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "edit_current_value", value=escape(product.description)),
                reply_markup=cancel,
            )
        # Wait for an answer
        description = self.__wait_for_regex(r"(.*)", cancellable=bool(product))

        # Ask product category
        self.bot.send_message(
            self.chat.id, self.loc.get("ask_product_category"))
        if product:
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "edit_current_value", value=escape(product.category)),
                reply_markup=cancel,
            )
        category = self.__wait_for_regex(r"(.*)", cancellable=bool(product))
        # Ask for the product price
        self.bot.send_message(self.chat.id, self.loc.get("ask_product_price"))
        # Display the current name if you're editing an existing product
        if product:
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "edit_current_value",
                    value=(
                        str(self.Price(product.price))
                        if product.price is not None
                        else "Non in vendita"
                    ),
                ),
                reply_markup=cancel,
            )
        # Wait for an answer
        price = self.__wait_for_regex(
            r"([0-9]+(?:[.,][0-9]{1,2})?|[Xx])", cancellable=True
        )
        # If the price is skipped
        if isinstance(price, CancelSignal):
            pass
        elif price.lower() == "x":
            price = None
        else:
            price = self.Price(price)
        if not isinstance(price, CancelSignal) and price is not None:
            price = int(price)
        # ask for the product quantity
        self.bot.send_message(
            self.chat.id, self.loc.get("ask_product_quantity"))
        if product:
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "edit_current_value",
                    value=product.quantity),
                reply_markup=cancel)
        quantity = self.__wait_for_regex(
            r"([0-9]+)", cancellable=bool(product))
        if isinstance(quantity, CancelSignal):
            pass
        elif quantity:
            quantity = int(quantity)
        # ask for the product notes
        self.bot.send_message(self.chat.id, self.loc.get("ask_product_notes"))
        if product:
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "edit_current_value",
                    value=escape(product.notes),
                    reply_markup=cancel,
                ),
            )
        notes = self.__wait_for_regex(r"(.*)", cancellable=bool(product))

        # Ask for the product image
        self.bot.send_message(
            self.chat.id,
            self.loc.get("ask_product_image"), reply_markup=cancel
        )
        # Wait for an answer
        photo_list = self.__wait_for_photo(cancellable=True)
        # If a new product is being added...
        if not product:
            # Create the db record for the product
            # noinspection PyTypeChecker
            product = db.Product(
                name=name,
                description=description,
                price=price,
                deleted=False,
                quantity=quantity,
                category=category,
                notes=notes,
            )
            # Add the record to the database
            self.session.add(product)
        # If a product is being edited...
        else:
            # Edit the record with the new values
            product.name = name if not isinstance(
                name, CancelSignal) else product.name
            product.description = (
                description
                if not isinstance(description, CancelSignal)
                else product.description
            )
            product.price = (
                price if not isinstance(price, CancelSignal) else product.price
            )
            product.notes = (
                notes if not isinstance(notes, CancelSignal) else product.notes
            )
            product.quantity = (
                quantity if not isinstance(
                    quantity, CancelSignal) else product.quantity
            )
            product.category = (
                category if not isinstance(
                    category, CancelSignal) else product.category
            )
        # If a photo has been sent...
        if isinstance(photo_list, list):
            # Find the largest photo id
            largest_photo = photo_list[0]
            for photo in photo_list[1:]:
                if photo.width > largest_photo.width:
                    largest_photo = photo
            # Get the file object associated with the photo
            photo_file = self.bot.get_file(largest_photo.file_id)
            # Notify the user that the bot is downloading the image
            # and might be inactive for a while
            self.bot.send_message(
                self.chat.id, self.loc.get("downloading_image"))
            self.bot.send_chat_action(self.chat.id, action="upload_photo")
            # Set the image for that product
            product.set_image(photo_file)
        # Commit the session changes
        self.session.commit()
        # Notify the user
        self.bot.send_message(
            self.chat.id, self.loc.get("success_product_edited"))

    def __delete_product_menu(self):
        log.debug("Displaying __delete_product_menu")
        # Get the products list from the db
        products = self.session.query(db.Product).filter_by(deleted=False).all()
        # Create a list of product names
        product_names = [product.name for product in products]
        # Insert at the start of the list the Cancel button
        product_names.insert(0, self.loc.get("menu_cancel"))
        # Create a keyboard using the product names
        keyboard = [
            [telegram.KeyboardButton(
                product_name)] for product_name in product_names
        ]
        # Send the previously created keyboard to the user
        # (ensuring it can be clicked only 1 time)
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_admin_select_product_to_delete"),
            reply_markup=telegram.ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True),
        )
        # Wait for a reply from the user
        selection = self.__wait_for_specific_message(
            product_names, cancellable=True)
        if isinstance(selection, CancelSignal):
            # Exit the menu
            return
        else:
            # Find the selected product
            product = (
                self.session.query(db.Product)
                .filter_by(name=selection, deleted=False)
                .one()
            )
            # "Delete" the product by setting the deleted flag to true
            product.deleted = True
            self.session.commit()
            # Notify the user
            self.bot.send_message(
                self.chat.id, self.loc.get("success_product_deleted"))

    def __orders_menu(self):
        """Display a live flow of orders."""
        log.debug("Displaying __orders_menu")
        # Create a cancel and a stop keyboard
        stop_keyboard = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_stop"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        cancel_keyboard = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_cancel"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        # Send a small intro message on the Live Orders mode
        # Remove the keyboard with the first message... (#39)
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_live_orders_start"),
            reply_markup=telegram.ReplyKeyboardRemove(),
        )
        # ...and display a small inline keyboard with the following one
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_live_orders_stop"),
            reply_markup=stop_keyboard,
        )
        # Create the order keyboard
        order_keyboard = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_complete"), callback_data="order_complete"
                    )
                ],
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_refund"), callback_data="order_refund"
                    )
                ],
            ]
        )
        # Display the past pending orders
        orders = (
            self.session.query(db.Order)
            .filter_by(delivery_date=None, refund_date=None)
            .join(db.Transaction)
            .join(db.User)
            .all()
        )
        # Create a message for every one of them
        for order in orders:
            # Send the created message
            self.bot.send_message(
                self.chat.id, order.text(w=self), reply_markup=order_keyboard
            )
        # Set the Live mode flag to True
        self.admin.live_mode = True
        # Commit the change to the database
        self.session.commit()
        while True:
            # Wait for any message to stop the listening mode
            update = self.__wait_for_inlinekeyboard_callback(cancellable=True)
            # If the user pressed the stop button, exit listening mode
            if isinstance(update, CancelSignal):
                # Stop the listening mode
                self.admin.live_mode = False
                break
            # Find the order
            order_id = re.search(
                self.loc.get("order_number").replace("{id}", "([0-9]+)"),
                update.message.text,
            ).group(1)
            order = self.session.query(db.Order).get(order_id)
            item: db.OrderItem = (
                self.session.query(db.OrderItem)
                .filter(db.OrderItem.order_id == order_id)
                .one_or_none()
            )
            # Check if the order hasn't been already cleared
            if order.delivery_date is not None or order.refund_date is not None:
                # Notify the admin and skip that order
                self.bot.edit_message_text(
                    self.chat.id, self.loc.get("error_order_already_cleared")
                )
                break
            # If the user pressed the complete order button, complete the order
            if update.data == "order_complete":
                # Mark the order as complete
                order.delivery_date = datetime.datetime.now()
                # Commit the transaction
                self.session.commit()
                # Update order message
                self.bot.edit_message_text(
                    order.text(w=self),
                    chat_id=self.chat.id,
                    message_id=update.message.message_id,
                )
                # Notify the user of the completition
                self.bot.send_message(
                    order.user_id,
                    self.loc.get(
                        "notification_order_completed",
                        order=order.text(w=self, user=True),
                    ),
                )
            # If the user pressed the refund order button, refund the order...
            elif update.data == "order_refund":
                # Ask for a refund reason
                reason_msg = self.bot.send_message(
                    self.chat.id,
                    self.loc.get("ask_refund_reason"),
                    reply_markup=cancel_keyboard,
                )
                # Wait for a reply
                reply = self.__wait_for_regex("(.*)", cancellable=True)
                # If the user pressed the cancel button, cancel the refund
                if isinstance(reply, CancelSignal):
                    # Delete the message asking for the refund reason
                    self.bot.delete_message(
                        self.chat.id, reason_msg.message_id)
                    continue
                # Mark the order as refunded
                order.refund_date = datetime.datetime.now()
                # Save the refund reason
                order.refund_reason = reply
                # Refund the credit, reverting the old transaction
                order.transaction.refunded = True
                # Update the user's credit
                order.user.recalculate_credit()
                # Commit the changes
                self.session.commit()
                # Update the order message
                self.bot.edit_message_text(
                    order.text(w=self),
                    chat_id=self.chat.id,
                    message_id=update.message.message_id,
                )
                # Notify the user of the refund
                self.bot.send_message(
                    order.user_id,
                    self.loc.get(
                        "notification_order_refunded",
                        order=order.text(w=self, user=True),
                    ),
                )
                # Notify the admin of the refund
                self.bot.send_message(
                    self.chat.id,
                    self.loc.get(
                        "success_order_refunded", order_id=order.order_id),
                )

    def __create_transaction(self):
        """Edit manually the credit of an user."""
        log.debug("Displaying __create_transaction")
        # Make the admin select an user
        user = self.__user_select()
        # Allow the cancellation of the operation
        if isinstance(user, CancelSignal):
            return
        # Create an inline keyboard with a single cancel button
        cancel = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_cancel"), callback_data="cmd_cancel"
                    )
                ]
            ]
        )
        # Request from the user the amount of money to be credited manually
        self.bot.send_message(
            self.chat.id, self.loc.get("ask_credit"), reply_markup=cancel
        )
        # Wait for an answer
        reply = self.__wait_for_regex(
            r"(-? ?[0-9]+(?:[.,][0-9]{1,2})?)", cancellable=True
        )
        # Allow the cancellation of the operation
        if isinstance(reply, CancelSignal):
            return
        # Convert the reply to a price object
        price = self.Price(reply)
        # Ask the user for notes
        self.bot.send_message(
            self.chat.id,
            self.loc.get("ask_transaction_notes"), reply_markup=cancel
        )
        # Wait for an answer
        reply = self.__wait_for_regex(r"(.*)", cancellable=True)
        # Allow the cancellation of the operation
        if isinstance(reply, CancelSignal):
            return
        # Create a new transaction
        transaction = db.Transaction(
            user=user, value=int(price), provider="Manual", notes=reply
        )
        self.session.add(transaction)
        # Change the user credit
        user.recalculate_credit()
        # Commit the changes
        self.session.commit()
        # Notify the user of the credit/debit
        self.bot.send_message(
            user.user_id,
            self.loc.get(
                "notification_transaction_created",
                transaction=transaction.text(w=self)
            ),
        )
        # Notify the admin of the success
        self.bot.send_message(
            self.chat.id,
            self.loc.get(
                "success_transaction_created",
                transaction=transaction.text(w=self)
            ),
        )

    def __help_menu(self):
        """Help menu. Allows the user to ask for assistance, get a guide or see some
        info about the bot."""
        log.debug("Displaying __help_menu")
        # Create a keyboard with the user help menu
        keyboard = [
            [telegram.KeyboardButton(self.loc.get("menu_contact_shopkeeper"))],
            [telegram.KeyboardButton(self.loc.get("menu_cancel"))],
        ]
        # Send the previously created keyboard to the user (ensuring it
        # can be clicked only 1 time)
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_open_help_menu"),
            reply_markup=telegram.ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True),
        )
        # Wait for a reply from the user
        selection = self.__wait_for_specific_message(
            [self.loc.get("menu_guide"),
            self.loc.get("menu_contact_shopkeeper")],
            cancellable=True,
        )
        # If the user has selected the Guide option...
        if selection == self.loc.get("menu_guide"):
            # Send them the bot guide
            self.bot.send_message(self.chat.id, self.loc.get("help_msg"))
        # If the user has selected the Order Status option...
        elif selection == self.loc.get("menu_contact_shopkeeper"):
            # Find the list of available shopkeepers
            shopkeepers = (
                self.session.query(db.Admin)
                .filter_by(display_on_help=True)
                .join(db.User)
                .all()
            )
            # Create the string
            shopkeepers_string = "\n".join(
                [admin.user.mention() for admin in shopkeepers]
            )
            # Send the message to the user
            self.bot.send_message(
                self.chat.id,
                self.loc.get(
                    "contact_shopkeeper",
                    shopkeepers=shopkeepers_string),
            )
        # If the user has selected the Cancel option
        # the function will return immediately

    def __transaction_pages(self):
        """Display the latest transactions, in pages."""
        log.debug("Displaying __transaction_pages")
        # Page number
        page = 0
        # Create and send a placeholder message to be populated
        message = self.bot.send_message(
            self.chat.id, self.loc.get("loading_transactions")
        )
        # Loop used to move between pages
        while True:
            # Retrieve the 10 transactions in that page
            transactions = (
                self.session.query(db.Transaction)
                .order_by(db.Transaction.transaction_id.desc())
                .limit(10)
                .offset(10 * page)
                .all()
            )
            # Create a list to be converted in inline keyboard markup
            inline_keyboard_list = [[]]
            # Don't add a previous page button if this is the first page
            if page != 0:
                # Add a previous page button
                inline_keyboard_list[0].append(
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_previous"), callback_data="cmd_previous"
                    )
                )
            # Don't add a next page button if this is the last page
            if len(transactions) == 10:
                # Add a next page button
                inline_keyboard_list[0].append(
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_next"), callback_data="cmd_next"
                    )
                )
            # Add a Done button
            inline_keyboard_list.append(
                [
                    telegram.InlineKeyboardButton(
                        self.loc.get("menu_done"), callback_data="cmd_done"
                    )
                ]
            )
            # Create the inline keyboard markup
            inline_keyboard = telegram.InlineKeyboardMarkup(inline_keyboard_list)
            # Create the message text
            transactions_string = "\n".join(
                [transaction.text(w=self) for transaction in transactions]
            )
            text = self.loc.get(
                "transactions_page", page=page + 1, transactions=transactions_string
            )
            # Update the previously sent message
            self.bot.edit_message_text(
                chat_id=self.chat.id,
                message_id=message.message_id,
                text=text,
                reply_markup=inline_keyboard,
            )
            # Wait for user input
            selection = self.__wait_for_inlinekeyboard_callback()
            # If Previous was selected...
            if selection.data == "cmd_previous" and page != 0:
                # Go back one page
                page -= 1
            # If Next was selected...
            elif selection.data == "cmd_next" and len(transactions) == 10:
                # Go to the next page
                page += 1
            # If Done was selected...
            elif selection.data == "cmd_done":
                # Break the loop
                break

    def __transactions_file(self):
        """Generate a .csv file containing the list of all transactions."""
        log.debug("Generating __transaction_file")
        # Retrieve all the transactions
        transactions = (
            self.session.query(db.Transaction)
            .order_by(db.Transaction.transaction_id)
            .all()
        )
        # Create the file if it doesn't exists
        try:
            with open(f"transactions_{self.chat.id}.csv", "x"):
                pass
        except IOError:
            pass
        # Write on the previously created file
        with open(f"transactions_{self.chat.id}.csv", "w") as file:
            # Write an header line
            file.write(
                f"UserID;"
                f"TransactionValue;"
                f"TransactionNotes;"
                f"Provider;"
                f"ChargeID;"
                f"SpecifiedName;"
                f"SpecifiedPhone;"
                f"SpecifiedEmail;"
                f"Refunded?\n"
            )
            # For each transaction; write a new line on file
            for transaction in transactions:
                file.write(
                    f"{transaction.user_id if transaction.user_id is not None else ''};"
                    f"{transaction.value if transaction.value is not None else ''};"
                    f"{transaction.notes if transaction.notes is not None else ''};"
                    f"{transaction.provider if transaction.provider is not None else ''};"
                    f"{transaction.provider_charge_id if transaction.provider_charge_id is not None else ''};"
                    f"{transaction.payment_name if transaction.payment_name is not None else ''};"
                    f"{transaction.payment_phone if transaction.payment_phone is not None else ''};"
                    f"{transaction.payment_email if transaction.payment_email is not None else ''};"
                    f"{transaction.refunded if transaction.refunded is not None else ''}\n"
                )
        # Describe the file to the user
        self.bot.send_message(self.chat.id, self.loc.get("csv_caption"))
        # Reopen the file for reading
        with open(f"transactions_{self.chat.id}.csv") as file:
            # Send the file via a manual request to Telegram
            requests.post(
                f"https://api.telegram.org/bot{self.cfg['Telegram']['token']}/sendDocument",
                files={"document": file},
                params={"chat_id": self.chat.id, "parse_mode": "HTML"},
            )
        # Delete the created file
        os.remove(f"transactions_{self.chat.id}.csv")

    def __add_admin(self):
        """Add an administrator to the bot."""
        log.debug("Displaying __add_admin")
        # Let the admin select an administrator to promote
        user = self.__user_select()
        # Allow the cancellation of the operation
        if isinstance(user, CancelSignal):
            return
        # Check if the user is already an administrator
        admin = self.session.query(db.Admin).filter_by(user=user).one_or_none()
        if admin is None:
            # Create the keyboard to be sent
            keyboard = telegram.ReplyKeyboardMarkup(
                [[self.loc.get("emoji_yes"), self.loc.get("emoji_no")]],
                one_time_keyboard=True,
            )
            # Ask for confirmation
            self.bot.send_message(
                self.chat.id,
                self.loc.get("conversation_confirm_admin_promotion"),
                reply_markup=keyboard,
            )
            # Wait for an answer
            selection = self.__wait_for_specific_message(
                [self.loc.get("emoji_yes"), self.loc.get("emoji_no")]
            )
            # Proceed only if the answer is yes
            if selection == self.loc.get("emoji_no"):
                return
            # Create a new admin
            admin = db.Admin(
                user=user,
                edit_products=False,
                receive_orders=False,
                create_transactions=False,
                is_owner=False,
                display_on_help=False,
            )
            self.session.add(admin)
        # Send the empty admin message and record the id
        message = self.bot.send_message(
            self.chat.id, self.loc.get("admin_properties", name=str(admin.user))
        )
        # Start accepting edits
        while True:
            # Create the inline keyboard with the admin status
            inline_keyboard = telegram.InlineKeyboardMarkup(
                [
                    [
                        telegram.InlineKeyboardButton(
                            f"{self.loc.boolmoji(admin.edit_products)} {self.loc.get('prop_edit_products')}",
                            callback_data="toggle_edit_products",
                        )
                    ],
                    [
                        telegram.InlineKeyboardButton(
                            f"{self.loc.boolmoji(admin.receive_orders)} {self.loc.get('prop_receive_orders')}",
                            callback_data="toggle_receive_orders",
                        )
                    ],
                    [
                        telegram.InlineKeyboardButton(
                            f"{self.loc.boolmoji(admin.create_transactions)} {self.loc.get('prop_create_transactions')}",
                            callback_data="toggle_create_transactions",
                        )
                    ],
                    [
                        telegram.InlineKeyboardButton(
                            f"{self.loc.boolmoji(admin.display_on_help)} {self.loc.get('prop_display_on_help')}",
                            callback_data="toggle_display_on_help",
                        )
                    ],
                    [
                        telegram.InlineKeyboardButton(
                            self.loc.get("menu_done"), callback_data="cmd_done"
                        )
                    ],
                ]
            )
            # Update the inline keyboard
            self.bot.edit_message_reply_markup(
                message_id=message.message_id,
                chat_id=self.chat.id,
                reply_markup=inline_keyboard,
            )
            # Wait for an user answer
            callback = self.__wait_for_inlinekeyboard_callback()
            # Toggle the correct property
            if callback.data == "toggle_edit_products":
                admin.edit_products = not admin.edit_products
            elif callback.data == "toggle_receive_orders":
                admin.receive_orders = not admin.receive_orders
            elif callback.data == "toggle_create_transactions":
                admin.create_transactions = not admin.create_transactions
            elif callback.data == "toggle_display_on_help":
                admin.display_on_help = not admin.display_on_help
            elif callback.data == "cmd_done":
                break
        self.session.commit()

    def __language_menu(self):
        """Select a language."""
        log.debug("Displaying __language_menu")
        keyboard = []
        options: Dict[str, str] = {}
        # https://en.wikipedia.org/wiki/List_of_language_names
        if "en" in self.cfg["Language"]["enabled_languages"]:
            lang = "???????? English"
            keyboard.append([telegram.KeyboardButton(lang)])
            options[lang] = "en"
        # Send the previously created keyboard to the user (ensuring it can be clicked only 1 time)
        self.bot.send_message(
            self.chat.id,
            self.loc.get("conversation_language_select"),
            reply_markup=telegram.ReplyKeyboardMarkup(keyboard, one_time_keyboard=True),
        )
        # Wait for an answer
        response = self.__wait_for_specific_message(list(options.keys()))
        # Set the language to the corresponding value
        # Recreate the localization object
        self.__create_localization()

    def __create_localization(self):
        # Check if the user's language is enabled; if it isn't, change it to the default
        if self.telegram_user.language_code not in self.cfg["Language"]["enabled_languages"]:
            log.debug(
                f"User's language '{self.user.language}' is not enabled, changing it to the default"
            )
            self.user.language = self.cfg["Language"]["default_language"]
        class Localization:
            def __init__(self, code, **kwrgs):
                if code == "en":
                    self._mode = en
                else:
                    self._mode = heb

            def get(self, arg):
                return getattr(self._mode, arg)

        self.loc = Localization(
            code=self.telegram_user.language_code,
            fallback=self.cfg["Language"]["fallback_language"],
            replacements={
                "user_string": str(self.user),
                "today": datetime.datetime.now().strftime("%a %d %b %Y"),
            },
        )

    def __graceful_stop(self, stop_trigger: StopSignal):
        """Handle the graceful stop of the thread."""
        log.debug("Gracefully stopping the conversation")
        # If the session has expired...
        if stop_trigger.reason == "timeout":
            # Notify the user that the session has expired and remove the keyboard
            self.bot.send_message(
                self.chat.id,
                self.loc.get("conversation_expired"),
                reply_markup=telegram.ReplyKeyboardRemove(),
            )
        # If a restart has been requested...
        # Do nothing.
        # Close the database session
        self.session.close()
        # End the process
        sys.exit(0)
