import csv
import os
import tempfile
import telegram
from telegram import InlineKeyboardMarkup
from telegram import InlineKeyboardButton
import worker2
from pathlib import Path
import _signals
import utils
CancelSignal = _signals.CancelSignal
StopSignal = _signals.StopSignal
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def product_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    add = "product_add"
    edit = "product_edit"
    delete = "product_delete"
    keyboard = [
        [
            InlineKeyboardButton(worker.loc.get("product_add"), callback_data=add),
            InlineKeyboardButton(worker.loc.get("product_edit"), callback_data=edit),
        ],
        [
            InlineKeyboardButton(worker.loc.get("product_delete"), callback_data=delete),
        ],
        worker.cancel_list
    ]
    if not selection:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("open_product_menu"),
            reply_markup=InlineKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    else:
        r = selection.edit_message_text(
            worker.loc.get("open_product_menu"),
            reply_markup=InlineKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    if selection.data != add:
        prods = worker.list_products()
        # check if product available to delete/edit
        if not prods:
            selection.edit_message_text(
                worker.loc.get("products_not_exists")
            )
            return worker.admin_product_menu()
    if selection.data == add:
        # ask for product name
        r = selection.edit_message_text(
            worker.loc.get("product_add_name"),
            reply_markup=worker.cancel_marked
        )
        worker.todelete.append(r.message_id)
        name_r = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(name_r, telegram.Update):
            return worker.admin_product_menu(selection=name_r.callback_query)

        # ask for product price
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_add_price"),
            reply_markup=worker.cancel_marked
        )
        worker.todelete.append(r.message_id)
        price_r = worker.wait_for_regex(r"([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
        if isinstance(price_r, telegram.Update):
            return worker.admin_product_menu(selection=price_r.callback_query)
        # ask for product description
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_add_desc"),
            reply_markup=worker.cancel_marked
        )
        worker.todelete.append(r.message_id)
        description = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(description, telegram.Update):
            return worker.admin_product_menu(selection=description.callback_query)
        # ask for number of SMS associated with the product package
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_add_number_sms"),
            reply_markup=worker.cancel_marked
        )
        worker.todelete.append(r.message_id)
        volume = worker.wait_for_regex("([0-9]+)", cancellable=True)
        if isinstance(volume, telegram.Update):
            return worker.admin_product_menu(selection=volume.callback_query)
        # TODO clear messages logs
        """for i in worker.todelete[:-1]:
            worker.bot.delete_message(i)
        worker.todelete = [worker.todelete[-1]]"""
        # worker.bot.delete_message()
        data = {"name": name_r, "price": int(price_r), "desc": description, "volume": int(volume)}
        worker.create_or_update_product(data=data)
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_add_success")
        )
        return worker.admin_menu()

    elif selection.data == edit:
        cancel_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(worker.loc.get("menu_cancel"), callback_data="cmd_cancel"),
            InlineKeyboardButton(worker.loc.get("menu_skip"), callback_data="cmd_skip")
        ]])
        data, keyboard = utils.get_product_data(prods)
        keyboard.append(worker.cancel_list)
        selection.edit_message_text(
            worker.loc.get("product_edit_prompt"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_product_menu(selection=selection)
        prod = data[selection.data]
        old_name = prod["title"]
        selection.edit_message_text(
            worker.loc.get("product_edit_name").format(old_name),
            reply_markup=cancel_markup
        )
        name_r = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(name_r, telegram.Update):
            if name_r.callback_query.data == "cmd_skip":
                pass
            else:
                return worker.admin_product_menu(selection=name_r.callback_query)

        # ask for product price
        old_price = prod["price"]
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_edit_price").format(old_price),
            reply_markup=cancel_markup
        )
        worker.todelete.append(r.message_id)
        price_r = worker.wait_for_regex(r"([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
        if isinstance(price_r, telegram.Update):
            if price_r.callback_query.data == "cmd_skip":
                pass
            else:
                return worker.admin_product_menu(selection=price_r.callback_query)

        # ask for product description
        old_desc = prod["description"]
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_edit_desc").format(old_desc),
            reply_markup=cancel_markup
        )
        worker.todelete.append(r.message_id)
        description = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(description, telegram.Update):
            if description.callback_query.data == "cmd_skip":
                pass
            else:
                return worker.admin_product_menu(selection=description.callback_query)

        # ask for number of SMS associated with the product package
        old_vol = prod.get("volume", 1000)
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_edit_number_sms").format(old_vol),
            reply_markup=cancel_markup
        )
        worker.todelete.append(r.message_id)
        volume = worker.wait_for_regex("([0-9]+)", cancellable=True)
        if isinstance(volume, telegram.Update):
            if volume.callback_query.data == "cmd_skip":
                pass
            else:
                return worker.admin_product_menu(selection=volume.callback_query)

        name = old_name if isinstance(name_r, telegram.Update) else name_r
        price = old_price if isinstance(price_r, telegram.Update) else int(price_r)
        desc = old_desc if isinstance(description, telegram.Update) else description
        volume = old_vol if isinstance(volume, telegram.Update) else int(volume)
        product_id = prod["product_id"]
        data = {"name": name, "price": price, "desc": desc, "volume": volume, "product_id": product_id}
        worker.create_or_update_product(data, update=True)
        r = worker.bot.send_message(
            worker.chat.id, worker.loc.get("product_edit_success")
        )
        return

    elif selection.data == delete:
        data, keyboard = utils.get_product_data(prods)
        cancel_markup = [InlineKeyboardButton(worker.loc.get("menu_cancel"), callback_data="cmd_cancel")]
        keyboard.append(cancel_markup)
        selection.edit_message_text(
            worker.loc.get("product_delete_prompt"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_product_menu(selection=selection)
        prod = data[selection.data]
        prod = prod["product_id"]
        worker.delete_product(prod)
        selection.edit_message_text(
            worker.loc.get("product_delete_success")
        )
        return worker.admin_product_menu()


def addcredit_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    """Update the credit for users"""
    users = worker.get_users()
    data, keyboard = utils.get_users_data(users, exclude=worker.telegram_user.id)
    if not users:
        selection.edit_message_text(
            worker.loc.get("users_not_exists")
        )
        return worker.admin_menu()
    keyboard.append(worker.cancel_list)
    selection.edit_message_text(
        worker.loc.get("add_credit_prompt"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    user = data[selection.data]

    selection.edit_message_text(
        worker.loc.get("add_credit_amount").format(user["balance"]),
        reply_markup=worker.cancel_marked
    )
    price_r = worker.wait_for_regex(r"([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
    if isinstance(price_r, telegram.Update):
        return worker.admin_menu(button=price_r.callback_query)
    price_r = int(price_r.strip())
    res = worker.update_balace(selection.data, price_r)
    selection.edit_message_text(
        res["msg"]
    )
    return worker.admin_menu()


def user_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    users = worker.get_users()
    if len(users) == 1:
        selection.edit_message_text(
            worker.loc.get("users_not_exists")
        )
        return worker.admin_menu()
    buttons = [
        [
            InlineKeyboardButton(worker.loc.get("user_ban"), callback_data="ban"),
            InlineKeyboardButton(worker.loc.get("user_unban"), callback_data="unban"),
        ],
        [
            InlineKeyboardButton(worker.loc.get("user_promote"), callback_data="promote"),
            InlineKeyboardButton(worker.loc.get("user_pm"), callback_data="pm"),
        ],
        [
            InlineKeyboardButton(worker.loc.get("user_pms"), callback_data="pms")
        ],
        worker.cancel_list
    ]
    if selection:
        selection.edit_message_text(
            worker.loc.get("user_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("user_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data != "cmd_cancel":
        data, keyboard = utils.get_users_data(users, exclude=worker.telegram_user.id)
        if not data:
            selection.edit_message_text(
                worker.loc.get("users_not_exists"),
            )
            return worker.admin_menu()
        keyboard.append(worker.cancel_list)
        keyboard_done = list(keyboard)
        keyboard_done.append([InlineKeyboardButton(worker.loc.get("menu_done"), callback_data="cmd_done")])
        keyboard_copy = list(keyboard_done)
        keyboard_done = InlineKeyboardMarkup(keyboard_done)
        keyboard = InlineKeyboardMarkup(keyboard)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    elif selection.data == "ban":
        selection.edit_message_text(
            worker.loc.get("user_ban_prompt"),
            reply_markup=keyboard
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_user_menu(selection=selection)
        user = data[selection.data]
        worker.ban(user["telegram_id"])
        selection.edit_message_text(worker.loc.get("user_banned"))
        return worker.admin_menu()

    elif selection.data == "unban":
        users = worker.get_banned_users()
        if not users:
            selection.edit_message_text(
                worker.loc.get("user_unban_failed")
            )
            return worker.admin_user_menu()
        data, keyboard = utils.get_users_data(users)
        keyboard.append(worker.cancel_list)
        keyboard = InlineKeyboardMarkup(keyboard)
        selection.edit_message_text(
            worker.loc.get("user_unban_prompt"),
            reply_markup=keyboard
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_user_menu(selection=selection)
        user = data[selection.data]
        worker.unban(user["telegram_id"])
        selection.edit_message_text(worker.loc.get("user_unbanned"))
        return worker.admin_menu()
    elif selection.data == "promote":
        data, keyboard = utils.get_users_data(users)
        keyboard.append(worker.cancel_list)
        keyboard = InlineKeyboardMarkup(keyboard)
        selection.edit_message_text(
            worker.loc.get("user_promote_prompt"),
            reply_markup=keyboard
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_user_menu(selection=selection)
        user = data[selection.data]
        status = user["status"]
        status = "VIP" if status == "regular" else "Regular"
        button = [
            [InlineKeyboardButton(status, callback_data="status")],
            worker.cancel_list
        ]
        selection.edit_message_text(
            worker.loc.get("user_promote_current_status").format(user["status"]),
            reply_markup=InlineKeyboardMarkup(button)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_user_menu(selection=selection)
        res = worker.change_status(user["telegram_id"])
        worker.bot.send_message(
            int(user["telegram_id"]),
            worker.loc.get("inform_status_change").format(status)
        )
        selection.edit_message_text(
            res["msg"]
        )
        return worker.admin_menu()

    elif selection.data == "pm":
        selection.edit_message_text(
            worker.loc.get("user_pm_prompt"),
            reply_markup=keyboard
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_user_menu(selection=selection)
        user_id = selection.data
        selection.edit_message_text(
            worker.loc.get("user_pm_message"),
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex(cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_user_menu(button=selection.callback_query)
        worker.bot.send_message(
            int(user_id), selection
        )
        worker.bot.send_message(
            worker.chat.id, worker.loc.get("user_pm_success")
        )
        return worker.admin_user_menu()

    elif selection.data == "pms":
        selection.edit_message_text(
            worker.loc.get("user_pms_prompt"),
            reply_markup=keyboard_done
        )
        selected = 0
        while True:
            selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
            if selection.data == "cmd_cancel":
                return worker.admin_user_menu(selection=selection)
            elif selection.data == "cmd_done":
                # check at least one user selected for the pm
                if not selected:
                    continue
                else:
                    break
            for kb in keyboard_copy:
                for k in kb:
                    if k.callback_data == selection.data:
                        if "✅" in k.text:
                            k.text = k.text.replace("✅", "")
                            selected -= 1
                        else:
                            k.text = k.text + " ✅"
                            selected += 1
            selection.edit_message_text(
                worker.loc.get("user_pms_prompt"),
                reply_markup=InlineKeyboardMarkup(keyboard_copy)
            )
        ids = []
        for kb in keyboard_copy:
            for k in kb:
                if "✅" in k.text and (k.callback_data != "cmd_done"):
                    ids.append(int(k.callback_data))
        selection.edit_message_text(
            worker.loc.get("user_pms_message"),
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_user_menu(selection=selection.callback_query)
        for user in ids:
            worker.bot.send_message(
                user, selection
            )
        worker.bot.send_message(
            worker.chat.id, worker.loc.get("user_pms_success")
        )


def promo_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    buttons = [
        [
            InlineKeyboardButton(worker.loc.get("coupon_add"), callback_data="add_coupon"),
            InlineKeyboardButton(worker.loc.get("coupon_delete"), callback_data="delete_coupon")
        ],
        worker.cancel_list
    ]
    if not selection:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("promo_menu_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        selection.edit_message_text(
            worker.loc.get("promo_menu_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    if selection.data == "add_coupon":
        selection.edit_message_text(
            worker.loc.get("promo_add_code"),
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_menu(button=selection)
        code = selection
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("promo_add_discount")
        )
        selection = worker.wait_for_regex("([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_menu(button=selection)
        discount = selection
        worker.create_coupon(code, discount)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("coupon_add_success")
        )
        return worker.admin_menu()
    elif selection.data == "delete_coupon":
        coupons = worker.get_coupons()
        if not coupons:
            selection.edit_message_text(
                worker.loc.get("coupons_not_exist")
            )
            return worker.admin_menu()
        data, keyboard = utils.get_coupons_data(coupons)
        keyboard.append(worker.cancel_list)
        selection.edit_message_text(
            worker.loc.get("coupon_delete_prompt"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_promo_menu(selection=selection)
        coupon = selection.data
        worker.delete_coupon(coupon)
        selection.edit_message_text(
            worker.loc.get("coupon_delete_success")
        )
        return worker.admin_promo_menu()


def csv_dump(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    users = worker.user_dump()
    file = open("dump.csv", newline="", mode="w")
    fieldnames = ["username", "id"]
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(users)
    selection.edit_message_text(
        worker.loc.get("csv_prepared")
    )
    file.close()
    worker.bot.send_document(
        worker.chat.id,
        document=open("dump.csv", "rb"),
        filename="users.csv"
    )
    os.remove(file.name)
    return worker.admin_menu()


def vippromo_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    buttons = [
        [
            InlineKeyboardButton(worker.loc.get("coupon_add"), callback_data="add_coupon"),
            InlineKeyboardButton(worker.loc.get("coupon_delete"), callback_data="delete_coupon")
        ],
        worker.cancel_list
    ]
    if not selection:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("vippromo_menu_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        selection.edit_message_text(
            worker.loc.get("vippromo_menu_prompt"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    if selection.data == "add_coupon":
        selection.edit_message_text(
            worker.loc.get("vippromo_add_code"),
            reply_markup=worker.cancel_marked
        )
        selection = worker.wait_for_regex("(.*)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_menu(button=selection)
        code = selection
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("vippromo_add_discount")
        )
        selection = worker.wait_for_regex("([0-9]+(?:[.,][0-9]+)?)", cancellable=True)
        if isinstance(selection, telegram.Update):
            return worker.admin_menu(button=selection)
        discount = selection
        worker.create_coupon(code, discount)
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("coupon_add_success")
        )
        return worker.admin_menu()
    elif selection.data == "delete_coupon":
        coupons = worker.getvip_coupons()
        if not coupons:
            selection.edit_message_text(
                worker.loc.get("vipcoupons_not_exist")
            )
            return worker.admin_menu()
        data, keyboard = utils.get_coupons_data(coupons)
        keyboard.append(worker.cancel_list)
        selection.edit_message_text(
            worker.loc.get("vipcoupon_delete_prompt"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
        if selection.data == "cmd_cancel":
            return worker.admin_promo_menu(selection=selection)
        coupon = selection.data
        worker.deletevip_coupon(coupon)
        selection.edit_message_text(
            worker.loc.get("coupon_delete_success")
        )
        return worker.admin_promo_menu()


def transaction_menu(worker: "worker2.Worker", selection: telegram.CallbackQuery = None):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(worker.loc.get("transaction_today"), callback_data="today"),
            InlineKeyboardButton(worker.loc.get("transaction_weekly"), callback_data="weekly")
        ],
        [
            InlineKeyboardButton(worker.loc.get("transaction_monthly"), callback_data="monthly"),
            InlineKeyboardButton(worker.loc.get("transaction_all"), callback_data="all")
        ],
        worker.cancel_list
    ])
    if selection:
        selection.edit_message_text(
            worker.loc.get("transaction_prompt"),
            reply_markup=buttons
        )
    else:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("transaction_prompt"),
            reply_markup=buttons
        )
    selection = worker.wait_for_inlinekeyboard_callback(cancellable=True)
    if selection.data == "cmd_cancel":
        return worker.admin_menu(button=selection)
    transactions = worker.transaction_times(day=selection.data)
    if not transactions:
        selection.edit_message_text(
            worker.loc.get("transactions_not_exist")
        )
        return worker.admin_transaction_menu()
    selection.edit_message_text(
        worker.loc.get("transactions_info")
    )
    for tran in transactions:
        worker.bot.send_message(
            worker.chat.id,
            worker.loc.get("transaction_details").format(**tran)
        )
    return worker.admin_transaction_menu()
