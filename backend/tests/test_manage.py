from __future__ import annotations


def test_manage_migrate_runs_create_tables(monkeypatch, capsys):
    import app.manage as manage

    calls: list[str] = []
    monkeypatch.setattr(manage, "create_tables", lambda: calls.append("create_tables"))

    result = manage.main(["migrate"])
    output = capsys.readouterr().out

    assert result == 0
    assert calls == ["create_tables"]
    assert "Schema migrations applied" in output
