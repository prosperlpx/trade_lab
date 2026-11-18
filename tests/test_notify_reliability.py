import urllib.error
import urllib.request

import pytest

from trade_lab.notify import NotifyError, send_telegram


@pytest.mark.parametrize(
    "code, uncertain",
    [(400, False), (429, False), (500, True), (503, True), (408, True), (425, True)],
)
def test_http_delivery_classification(monkeypatch, code, uncertain):
    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, code, "response", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(NotifyError) as info:
        send_telegram("token", "42", "hello")
    assert info.value.delivery_uncertain is uncertain


def test_network_failure_is_delivery_uncertain(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(NotifyError) as info:
        send_telegram("token", "42", "hello")
    assert info.value.delivery_uncertain is True
