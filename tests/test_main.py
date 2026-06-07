"""Tests for main.py."""
from unittest.mock import patch

import pytest

from src import main as main_module


def test_main_runs_mcp_stdio_transport():
    with patch("src.main.signal.signal") as mock_signal, \
            patch.object(main_module.mcp, "run") as mock_run:
        main_module.main()

    mock_signal.assert_called_once()
    mock_run.assert_called_once_with(transport="stdio")


def test_main_exits_cleanly_on_keyboard_interrupt():
    with patch.object(main_module.mcp, "run", side_effect=KeyboardInterrupt), \
            patch("src.main.sys.exit") as mock_exit:
        main_module.main()

    mock_exit.assert_called_once_with(0)


def test_main_prints_and_exits_on_startup_error(capsys):
    with patch.object(main_module.mcp, "run", side_effect=RuntimeError("boom")), \
            patch("src.main.sys.exit") as mock_exit:
        main_module.main()

    assert "Error starting MCP server: boom" in capsys.readouterr().err
    mock_exit.assert_called_once_with(1)


def test_sigterm_handler_exits_cleanly():
    captured = {}

    def capture_handler(_signum, handler):
        captured["handler"] = handler

    with patch("src.main.signal.signal", side_effect=capture_handler), \
            patch.object(main_module.mcp, "run"), \
            patch("src.main.sys.exit", side_effect=SystemExit(0)) as mock_exit:
        main_module.main()
        with pytest.raises(SystemExit):
            captured["handler"](15, None)

    mock_exit.assert_called_once_with(0)
