from abc import (
    ABC, abstractmethod
)


class Service(ABC):
    @abstractmethod
    def name(self):
        """return the service name"""

    @abstractmethod
    def packages(self):
        """return packages for this services"""


class Package:
    def __init__(self, name, min_price, min_qty, max_qty=None):
        self.name = name
        self.price = min_price
        self.minimum = min_qty
        self.maximum = max_qty


class TelegramService(Service):
    def name(self):
        return "Telegram"

    def packages(self):
        packList = [
            Package("Members Adding", 100, 1000),
            Package("Post Views", 50, 1000)
        ]
        return packList


def getServices():
    services = [
        TelegramService()
    ]
    return services

