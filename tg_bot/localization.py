import translations.en as en
import translations.heb as heb


class Localization:
    def __init__(self, code):
        if code == "en":
            self._mod = en
        else:
            self._mod = heb

    def get(self, arg) -> str:
        return getattr(self._mod, arg)
