import requests
import json
from pprint import pprint
from collections import defaultdict
import sqlite3


def getCrescitaly():
    db = sqlite3.connect("services.db", check_same_thread=False)
    cursor = db.cursor()

    query = "create table if not exists crescitaly(category text," \
            "name text, min integer, max integer, rate double, service text)"
    cursor.execute(query)
    db.commit()

    data = {
        "key": "221e1735400c6af1ce312cc8d2772452",
        "action": "services"
    }

    url = "https://crescitaly.com/api/v2"

    res = requests.get(url, data)
    info: list[dict] = res.json()
    insert = "insert into crescitaly values(?, ?, ?, ?, ?, ?)"
    for service in info:
        name = service.get("name")
        cat = service.get("category")
        rate = service.get("rate")
        mi = service.get("min")
        mx = service.get("max")
        serv = service.get("service")
        cursor.execute(insert, (cat, name, mi, mx, rate, serv))

    db.commit()


def getSMMstone():
    db = sqlite3.connect("services.db", check_same_thread=False)
    cursor = db.cursor()

    query = "create table if not exists stoneservices(category text," \
            "name text, min integer, max integer, rate double, service text, source int)"
    cursor.execute(query)
    db.commit()
    data = {
        "key": "e9c8000826bc8b53e7194bb86e753792",
        "action": "services"
    }

    url = "https://smmstone.com/api/v2"

    res = requests.get(url, data)
    info: list[dict] = res.json()
    insert = "insert into stoneservices values(?, ?, ?, ?, ?, ?, ?)"
    source = 1
    for service in info:
        name = service.get("name")
        cat = service.get("category")
        rate = service.get("rate")
        mi = service.get("min")
        mx = service.get("max")
        serv = service.get("service")
        cursor.execute(insert, (cat, name, mi, mx, rate, serv, source))

    db.commit()


def getPanelbotter():
    db = sqlite3.connect("services.db", check_same_thread=False)
    cursor = db.cursor()

    query = "create table if not exists panelbotter(category text," \
            "name text, min integer, max integer, rate double, service text)"
    cursor.execute(query)
    db.commit()
    data = {
        "key": "384238a44e959028094587820725c9bd",
        "action": "services"
    }

    url = "https://panelbotter.com/api/v2"

    res = requests.get(url, data)
    info: list[dict] = res.json()
    insert = "insert into panelbotter values(?, ?, ?, ?, ?, ?)"
    for service in info:
        name = service.get("name")
        cat = service.get("category")
        rate = service.get("rate")
        mi = service.get("min")
        mx = service.get("max")
        serv = service.get("service")
        cursor.execute(insert, (cat, name, mi, mx, rate, serv))

    db.commit()


def getTelegramadd():
    db = sqlite3.connect("services.db", check_same_thread=False)
    cursor = db.cursor()

    query = "create table if not exists telegramadd(category text," \
            "name text, min integer, max integer, rate double, service text)"
    cursor.execute(query)
    db.commit()
    data = {
        "key": "18a52c61c5e46e22d1aa0f7cb79e14c9",
        "action": "services"
    }

    url = "https://telegramadd.com/api/v2"

    res = requests.get(url, data)
    info: list[dict] = res.json()
    insert = "insert into telegramadd values(?, ?, ?, ?, ?, ?)"
    for service in info:
        name = service.get("name")
        cat = service.get("category")
        rate = service.get("rate")
        mi = service.get("min")
        mx = service.get("max")
        serv = service.get("service")
        cursor.execute(insert, (cat, name, mi, mx, rate, serv))

    db.commit()


getSMMstone()
getPanelbotter()
getTelegramadd()
getCrescitaly()
