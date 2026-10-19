from types import SimpleNamespace

import pytest

import fm_mcp.main as main


def test_main_runs_stateless_streamable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    run_calls = []
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            mcp_transport="streamable-http",
            mcp_host="0.0.0.0",
            mcp_port=8000,
            mcp_path="/mcp",
        ),
    )
    monkeypatch.setattr(main.mcp, "run", lambda **kwargs: run_calls.append(kwargs))

    main.main()

    assert run_calls == [{
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 8000,
        "path": "/mcp",
        "stateless_http": True,
        "json_response": True,
        "show_banner": False,
    }]


def test_main_keeps_stdio_for_local_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    run_calls = []
    monkeypatch.setattr(main, "settings", SimpleNamespace(mcp_transport="stdio"))
    monkeypatch.setattr(main.mcp, "run", lambda **kwargs: run_calls.append(kwargs))

    main.main()

    assert run_calls == [{"transport": "stdio"}]
