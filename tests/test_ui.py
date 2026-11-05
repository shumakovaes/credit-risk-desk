from urllib.parse import urlsplit
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration


def test_all_screens_and_form_submission(client, monkeypatch):
    # Keep the real API + PostgreSQL; only replace the HTTP transport.
    def transport(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, urlsplit(url).path, **kwargs)
    monkeypatch.setattr("httpx.request", transport)
    app = AppTest.from_file(Path("streamlit_app.py").resolve(), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 4
    app.sidebar.radio[0].set_value("Карточка клиента").run()
    assert not app.exception
    app.sidebar.radio[0].set_value("Проверка заявки").run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["evaluation"]["status"] == "manual_review"
    app.sidebar.radio[0].set_value("Калькулятор").run()
    app.button[0].click().run()
    assert not app.exception
    assert len(app.metric) == 3
    app.sidebar.radio[0].set_value("Журнал заявок").run()
    assert not app.exception
    assert len(app.metric) == 3
