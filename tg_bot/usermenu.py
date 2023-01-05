import worker2
import telegram
from telegram import InlineKeyboardMarkup
from telegram import InlineKeyboardButton
import _signals
import utils
import services
from pathlib import Path
import json
from collections import defaultdict
CancelSignal = _signals.CancelSignal
StopSignal = _signals.StopSignal


def servicemenu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    data = {
        "telegram1": "Telegram 1",
        "telegram2": "Telegram 2"
        # "spotify": "Spotify",
        # "instagram": "Instagram",
        # "twitter": "Twitter",
        # "facebook": "Facebook",
        # "tiktok": "Tiktok"
    }
    buttons = utils.buildmenubutton(data)
    if selection:
        selection.edit_message_text(
            worker.loc.get("servicePrompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        worker.bot.send_message(
            worker.chat.id, worker.loc.get("servicePrompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.user_menu(selection=selection)
    elif selection.data == "telegram1":
        """options for telegramadd powered by smmstone"""
        categories = utils.getServiceCategoriesStone("telegram")
        meta = {}
        i = 0
        for category in categories:
            meta[str(i)] = category
            i += 1
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("categoryPrompt"),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        category = meta.get(selection.data)
        customcategoryServices, actualcategoryServices = utils.serviceCategoryDataStone(category)
        meta = {}
        serviceData = {}
        for service in customcategoryServices:
            val = service["name"].replace(category, "")
            meta[service["service"]] = val
            serviceData[service["service"]] = service
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("serviceSelect").format(category),
            reply_markup=InlineKeyboardMarkup(buttons),
            # parse_mode=telegram.ParseMode.MARKDOWN_V2
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        service = serviceData.get(selection.data)  # the actual service for this category
        name = service.get("name")
        realservice = None
        for i in actualcategoryServices:
            if i.get("category") == category and i.get("name") == name:
                realservice = i
                realservice["source"] = 1
        meta = {
            "order": "Order 🛒"
        }
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("serviceDetails").format(**service),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        return worker.user_order_menu(selection=selection, order=realservice)

    elif selection.data == "telegram2":
        """options for panelbotter powered by crescitaly"""
        categories = utils.getServiceCategories("telegram")
        meta = {}
        i = 0
        for category in categories:
            meta[str(i)] = category
            i += 1
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("categoryPrompt"),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        category = meta.get(selection.data)
        customcategoryServices, actualcategoryServices = utils.serviceCategoryData(category)
        meta = {}
        serviceData = {}
        for service in customcategoryServices:
            val = service["name"].replace(category, "")
            meta[service["service"]] = val
            serviceData[service["service"]] = service
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("serviceSelect").format(category),
            reply_markup=InlineKeyboardMarkup(buttons),
            # parse_mode=telegram.ParseMode.MARKDOWN_V2
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        service = serviceData.get(selection.data)  # the actual service for this category
        realservice = None
        name = service.get("name")
        for i in actualcategoryServices:
            if i.get("category") == category and i.get("name") == name:
                realservice = i
                realservice["source"] = 2
        meta = {
            "order": "Order 🛒"
        }
        buttons = utils.buildmenubutton(meta)
        selection.edit_message_text(
            worker.loc.get("serviceDetails").format(**service),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.user_service_menu(selection=selection)
        return worker.user_order_menu(selection=selection, order=realservice or {})


def ordermenu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None, order: dict = None, adding=True):
    if adding:
        userdata = worker.get_user(worker.telegram_user.id)
        balance = int(userdata["balance"])
        if not balance:
            selection.edit_message_text(
                worker.loc.get("insufficientFunds"),
                parse_mode=telegram.ParseMode.MARKDOWN
            )
            return worker.user_menu()
        selection.edit_message_text(
            worker.loc.get("serviceQuantity").format(**order),
            parse_mode=telegram.ParseMode.MARKDOWN,
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex("([0-9]+)")
        if isinstance(selection, telegram.Update):
            return worker.user_menu(selection=selection.callback_query)
        minimum = int(order["min"])
        maximum = int(order["max"])
        qty = int(selection)
        if qty < minimum:
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("minimumQuantityError")
            )
            return worker.user_menu()
        elif qty > maximum:
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("maximumQuantityError")
            )
            return worker.user_menu()
        price = qty * float(order["rate"])
        if price > balance:
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("insufficientFunds4qty").format(price, balance)
            )
            return worker.user_menu()
        worker.bot.send_message(
            worker.chat.id, worker.loc.get("linkPrompt"),
            reply_markup=worker.cancel_marked
        )
        info = "Invalid link. Enter a link starting with https://"
        selection = worker.wait_for_regex("(^https://[0-9a-zA-Z.]+)", cancellable=True, info=info)
        if isinstance(selection, telegram.Update):
            return worker.user_menu(selection=selection.callback_query)
        link = selection.strip()
        data = order
        data["user_id"] = worker.telegram_user.id
        data["qty"] = qty
        data["link"] = link
        worker.update_balace(worker.telegram_user.id, price, charge=True)
        worker.addorder(data)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("orderAdded")
        )
        return worker.user_menu()
    meta = {
        "all": worker.loc.get("orderAll"),
        "status": worker.loc.get("orderStatus")
    }
    buttons = utils.buildmenubutton(meta)
    if selection:
        selection.edit_message_text(
            worker.loc.get("orderPanel"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("orderPanel"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.user_menu(selection=selection)
    elif selection.data == "all":
        orders = worker.get_orders()
        if not orders:
            selection.edit_message_text(
                worker.loc.get("orderUnavailable")
            )
            return worker.user_order_menu(adding=False)
        selection.edit_message_text(
            worker.loc.get("orderDetailsPromt")
        )
        for order in orders:
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("orderDetails").format(**order)
            )
        return worker.user_order_menu(adding=False)


def fundsmenu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    data = {
        "add": worker.loc.get("fundAddFunds"),
        "track": worker.loc.get("fundTrackFunds"),
        "bal": worker.loc.get("fundBalance")
    }
    buttons = utils.buildmenubutton(data)
    if selection:
        selection.edit_message_text(
            worker.loc.get("fundPrompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("fundPrompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.user_menu(selection=selection)
    elif selection.data == "add":
        selection.edit_message_text(
            worker.loc.get("fundAddInfo"),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        price = worker.wait_for_regex(r"([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
        if isinstance(price, telegram.Update):
            return worker.user_menu(selection=price.callback_query)
        info = worker.create_payment(worker.telegram_user.id, float(price.strip()))
        #  check for failed payments
        info = info["data"]
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("fundAddPayInfo").format(**info)
        )
        return worker.user_menu()
    elif selection.data == "track":
        selection.edit_message_text(
            worker.loc.get("fundTrackPrompt"),
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex(r"(.*)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.user_menu(selection=selection.callback_query)

        data = worker.track_payment(selection.strip())
        if not data:
            worker.bot.send_message(
                worker.chat.id,
                worker.loc.get("fundTrackInvalidID")
            )
            return worker.user_funds_menu()
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("fundTrackDetails").format(**data)
        )
        return worker.user_funds_menu()
    elif selection.data == "bal":
        data = worker.get_user(worker.telegram_user.id)
        balance = data["balance"]
        selection.edit_message_text(
            worker.loc.get("fundBalanceDetails").format(balance),
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        return worker.user_menu()


def paymenttrackmenu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    pass


def profilemanu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    pass


def myservices(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    """show the user subscriptions details"""
    pass
