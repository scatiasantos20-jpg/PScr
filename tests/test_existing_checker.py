from teatroapp_uploader.existing_checker import exists_hint_on_add_page


class _BodyLocator:
    def __init__(self, text: str):
        self._text = text

    def inner_text(self):
        return self._text


class _AnchorsLocator:
    def count(self):
        return 0


class _FakePage:
    def __init__(self, body: str):
        self._body = body

    def locator(self, sel: str):
        if sel == "body":
            return _BodyLocator(self._body)
        if sel == "a":
            return _AnchorsLocator()
        return _AnchorsLocator()


def test_exists_hint_detects_encontramos_pecas_text_even_with_typo():
    body = "Econtramos estas peças na plataforma: CARMEN MIRANDA"
    page = _FakePage(body)
    assert exists_hint_on_add_page(page, "CARMEN MIRANDA")
