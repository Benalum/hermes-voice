from starlette.testclient import TestClient

from hermes_voice.server.app import create_app
from tests.io.test_telegram_relay import FakeClient
from tests.server.test_orchestrator_loop import FakeStt, FakeTts, FakeVad
from tests.server.test_telegram_mode import make_config


class TestHealthz:
    def test_parrot_mode_reports_models_warm_after_startup(self) -> None:
        app = create_app(mode="parrot", vad=FakeVad(), stt=FakeStt(), tts=FakeTts())
        with TestClient(app) as client:
            body = client.get("/healthz").json()
        assert body == {"status": "ok", "mode": "parrot", "models": "warm", "telegram": "n/a"}

    def test_telegram_mode_reports_connection(self) -> None:
        app = create_app(
            mode="telegram",
            config=make_config(),
            telegram_client=FakeClient(),
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
        )
        with TestClient(app) as client:
            body = client.get("/healthz").json()
        assert body["telegram"] == "connected"
        assert body["models"] == "warm"

    def test_echo_mode_skips_models(self) -> None:
        app = create_app(mode="echo")
        with TestClient(app) as client:
            body = client.get("/healthz").json()
        assert body["models"] == "n/a"
