"""
Unit tests for core.py — daily_loss persistence, env_save/env_get, LiveFillLogger.
No external API calls; all file I/O uses tmp_path fixtures.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_daily_loss_file(monkeypatch, tmp_path):
    """Redirect _DAILY_LOSS_FILE to a temp path for the duration of the test."""
    import core
    p = str(tmp_path / "daily_loss.json")
    monkeypatch.setattr(core, "_DAILY_LOSS_FILE", p)
    return p


def _patch_env_file(monkeypatch, tmp_path):
    """Redirect ENV_FILE to a temp .env for the duration of the test."""
    import core
    p = str(tmp_path / ".env")
    monkeypatch.setattr(core, "ENV_FILE", p)
    return p


# ── load_daily_loss / save_daily_loss ─────────────────────────────────────────

class TestDailyLoss:
    def test_returns_zero_when_file_missing(self, monkeypatch, tmp_path):
        from core import load_daily_loss
        _patch_daily_loss_file(monkeypatch, tmp_path)
        assert load_daily_loss() == 0.0

    def test_returns_zero_for_stale_date(self, monkeypatch, tmp_path):
        from core import load_daily_loss
        path = _patch_daily_loss_file(monkeypatch, tmp_path)
        yesterday = str(date.today() - timedelta(days=1))
        Path(path).write_text(json.dumps({"date": yesterday, "realized_loss": 99.0}))
        assert load_daily_loss() == 0.0

    def test_returns_value_for_today(self, monkeypatch, tmp_path):
        from core import load_daily_loss
        path = _patch_daily_loss_file(monkeypatch, tmp_path)
        Path(path).write_text(json.dumps({"date": str(date.today()), "realized_loss": 42.5}))
        assert load_daily_loss() == pytest.approx(42.5)

    def test_returns_zero_on_corrupt_json(self, monkeypatch, tmp_path):
        from core import load_daily_loss
        path = _patch_daily_loss_file(monkeypatch, tmp_path)
        Path(path).write_text("NOT_JSON{{{")
        assert load_daily_loss() == 0.0

    def test_save_creates_file(self, monkeypatch, tmp_path):
        from core import save_daily_loss
        path = _patch_daily_loss_file(monkeypatch, tmp_path)
        save_daily_loss(123.45)
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["date"] == str(date.today())
        assert data["realized_loss"] == pytest.approx(123.45)

    def test_save_then_load_roundtrip(self, monkeypatch, tmp_path):
        from core import save_daily_loss, load_daily_loss
        _patch_daily_loss_file(monkeypatch, tmp_path)
        save_daily_loss(77.77)
        assert load_daily_loss() == pytest.approx(77.77)

    def test_save_atomic_no_leftover_tmp(self, monkeypatch, tmp_path):
        from core import save_daily_loss
        _patch_daily_loss_file(monkeypatch, tmp_path)
        save_daily_loss(1.0)
        assert not (tmp_path / "daily_loss.tmp").exists()


# ── env_save / env_get ────────────────────────────────────────────────────────

class TestEnvSaveGet:
    def test_save_and_get_roundtrip(self, monkeypatch, tmp_path):
        from core import env_save, env_get
        _patch_env_file(monkeypatch, tmp_path)
        # Clear the env var so os.environ doesn't shadow the .env read
        monkeypatch.delenv("TEST_KEY_GV", raising=False)
        env_save({"TEST_KEY_GV": "hello"})
        assert env_get("TEST_KEY_GV") == "hello"

    def test_save_updates_os_environ(self, monkeypatch, tmp_path):
        from core import env_save
        _patch_env_file(monkeypatch, tmp_path)
        monkeypatch.delenv("TEST_KEY_GV2", raising=False)
        env_save({"TEST_KEY_GV2": "world"})
        assert os.environ.get("TEST_KEY_GV2") == "world"

    def test_get_returns_default_when_missing(self, monkeypatch):
        from core import env_get
        monkeypatch.delenv("NO_SUCH_KEY_GV", raising=False)
        assert env_get("NO_SUCH_KEY_GV", "fallback") == "fallback"

    def test_environ_takes_priority_over_dotenv(self, monkeypatch, tmp_path):
        from core import env_save, env_get
        _patch_env_file(monkeypatch, tmp_path)
        env_save({"GV_PRIO": "from_file"})
        monkeypatch.setenv("GV_PRIO", "from_env")
        # os.environ should win
        assert env_get("GV_PRIO") == "from_env"


# ── LiveFillLogger ────────────────────────────────────────────────────────────

class TestLiveFillLogger:
    def _logger(self, tmp_path):
        from core import LiveFillLogger
        return LiveFillLogger(str(tmp_path / "fills.json"))

    def test_open_session_returns_string(self, tmp_path):
        logger = self._logger(tmp_path)
        sid = logger.open_session("AAPL")
        assert isinstance(sid, str) and len(sid) > 0

    def test_open_two_sessions_unique_ids(self, tmp_path):
        logger = self._logger(tmp_path)
        s1 = logger.open_session("AAPL")
        s2 = logger.open_session("MSFT")
        assert s1 != s2

    def test_record_fill_appears_in_file(self, tmp_path):
        logger = self._logger(tmp_path)
        sid = logger.open_session("AAPL")
        logger.record(sid, "buy", "AAPL", 10, 150.0)
        data = json.loads((tmp_path / "fills.json").read_text())
        session = next(s for s in data["sessions"] if s["id"] == sid)
        assert len(session["fills"]) == 1
        fill = session["fills"][0]
        assert fill["action"] == "buy"
        assert fill["qty"] == 10
        assert fill["price"] == pytest.approx(150.0)

    def test_close_session_sets_closed_at_and_pnl(self, tmp_path):
        logger = self._logger(tmp_path)
        sid = logger.open_session("MSFT")
        logger.close_session(sid, 25.50)
        data = json.loads((tmp_path / "fills.json").read_text())
        session = next(s for s in data["sessions"] if s["id"] == sid)
        assert session["closed_at"] is not None
        assert session["pnl"] == pytest.approx(25.50)

    def test_multiple_records_accumulate(self, tmp_path):
        logger = self._logger(tmp_path)
        sid = logger.open_session("GOOG")
        for i in range(3):
            logger.record(sid, "buy", "GOOG", 1, 100.0 + i)
        data = json.loads((tmp_path / "fills.json").read_text())
        session = next(s for s in data["sessions"] if s["id"] == sid)
        assert len(session["fills"]) == 3

    def test_tolerates_corrupt_file(self, tmp_path):
        """If the JSON file is corrupt, _load() returns a fresh empty store."""
        (tmp_path / "fills.json").write_text("GARBAGE")
        logger = self._logger(tmp_path)
        sid = logger.open_session("X")
        # Should not raise; file is rebuilt
        assert isinstance(sid, str)
