#!/usr/bin/env python3
# ruff: noqa: S101
"""共通テストフィクスチャ"""

import logging
import pathlib
import unittest.mock

import flask
import flask.testing
import pytest

import price_watch.managers.history
import price_watch.webapi.server


# === 環境モック ===
@pytest.fixture(scope="session", autouse=True)
def env_mock():
    """テスト環境用の環境変数モック"""
    with unittest.mock.patch.dict(
        "os.environ",
        {
            "TEST": "true",
            "NO_COLORED_LOGS": "true",
        },
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def slack_mock():
    """Slack API のモック"""
    with unittest.mock.patch("my_lib.notify.slack.slack_sdk.web.client.WebClient"):
        yield


# === データベースフィクスチャ ===
@pytest.fixture
def temp_data_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """一時データディレクトリ"""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def history_manager(temp_data_dir: pathlib.Path) -> price_watch.managers.history.HistoryManager:
    """初期化済みの HistoryManager"""
    manager = price_watch.managers.history.HistoryManager.create(temp_data_dir)
    manager.initialize()
    return manager


# === Web API フィクスチャ ===
@pytest.fixture
def app(
    history_manager: price_watch.managers.history.HistoryManager,
    tmp_path: pathlib.Path,
) -> flask.Flask:
    """Flask アプリケーション"""
    static_dir = tmp_path / "static"
    mock_config = unittest.mock.MagicMock()
    mock_config.webapp.external_url = None

    with unittest.mock.patch(
        "price_watch.webapi.cache.get_app_config",
        return_value=mock_config,
    ):
        app = price_watch.webapi.server.create_app(static_dir_path=static_dir)

    app.config["history_manager"] = history_manager
    return app


@pytest.fixture
def client(app: flask.Flask) -> flask.testing.FlaskClient:
    """Flask テストクライアント"""
    return app.test_client()


# === テストデータ ===
@pytest.fixture
def sample_item() -> dict:
    """サンプルアイテムデータ"""
    return {
        "name": "テスト商品",
        "url": "https://example.com/item/1",
        "store": "test-store.com",
        "price": 1000,
        "stock": 1,
        "thumb_url": None,
    }


# === ロギング ===
logging.getLogger("selenium.webdriver.remote").setLevel(logging.WARNING)
logging.getLogger("selenium.webdriver.common").setLevel(logging.DEBUG)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
