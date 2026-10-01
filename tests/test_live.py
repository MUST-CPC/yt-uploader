"""Unit tests for the live SSH output renderer (no network needed)."""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mustcpc.vps import LiveRenderer


def render(feeds):
    out = io.StringIO()
    r = LiveRenderer(out=out)
    for chunk in feeds:
        r.feed(chunk)
    r.finish()
    return out.getvalue()


def test_plain_lines():
    assert render(["a\n", "b\n"]) == "a\nb\n"


def test_split_lines_across_chunks():
    assert render(["hel", "lo\nworld\n"]) == "hello\nworld\n"


def test_carriage_return_redraws_one_line():
    got = render(["[UPLOAD] 1%\r[UPLOAD] 2%\r[UPLOAD] 3%\n"])
    assert got == "[UPLOAD] 1%\r[UPLOAD] 2%\r[UPLOAD] 3%\n"


def test_redraw_without_trailing_newline_gets_closed():
    got = render(["50%\r100%"])
    assert got == "50%\r100%\n"


def test_lone_redraw_gets_closed():
    assert render(["50%\r"]) == "50%\r\n"


def test_crlf_pair_is_single_line():
    assert render(["ok\r\nnext\n"]) == "ok\r\nnext\n"


def test_trailing_newline_not_duplicated():
    assert render(["done\n"]) == "done\n"


def test_run_live_streams_and_collects(monkeypatch, capsys):
    """run_live() through a real pipe, with sh standing in for ssh."""
    import mustcpc.vps as vpsmod
    from mustcpc.config import Config

    monkeypatch.setattr(vpsmod, "_ssh_prefix", lambda cfg: ["sh", "-c"])
    cfg = Config(vps_host="h", vps_user="u")
    res = vpsmod.run_live(
        cfg, "printf '50%%\\r100%%\\n'; printf 'https://youtu.be/abc\\n'"
    )
    assert res.ok
    assert "https://youtu.be/abc" in res.stdout
    out = capsys.readouterr().out
    assert "50%" in out and "100%" in out and "youtu.be/abc" in out


def test_run_live_failure(monkeypatch):
    import mustcpc.vps as vpsmod
    from mustcpc.config import Config

    monkeypatch.setattr(vpsmod, "_ssh_prefix", lambda cfg: ["sh", "-c"])
    cfg = Config(vps_host="h", vps_user="u")
    res = vpsmod.run_live(cfg, "echo boom; exit 3", check=False)
    assert not res.ok and res.returncode == 3
    try:
        vpsmod.run_live(cfg, "echo boom; exit 3")
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
