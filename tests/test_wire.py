# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
import random
import string

import pytest

from hornet.mesh import wire


def msg(**kw):
    base = dict(typ="A", ident="abcdef12", station="Stand 1", count=2, conf=87, ai="J", lat=51.05, lon=7.10, note="am Flugloch")
    base.update(kw)
    return wire.MeshMessage(**base)


def test_roundtrip():
    line = wire.encode(msg())
    assert line == "H3K1|A|abcdef12|Stand 1|2|87|J|51.05|7.10|am Flugloch"
    assert wire.parse(line) == msg()


def test_parse_ignores_device_name_prefix():
    assert wire.parse("Max Imker: " + wire.encode(msg())) == msg()


def test_encode_respects_byte_budget_with_multibyte_text():
    m = msg(note="äöü" * 60, station="Bienenstand Überlingen am Bodensee Süd")
    line = wire.encode(m, wire.LORA_MAX_BYTES)
    assert len(line.encode("utf-8")) <= wire.LORA_MAX_BYTES
    assert wire.parse(line) is not None


def test_encode_rejects_bad_input():
    with pytest.raises(ValueError):
        wire.encode(msg(typ="X"))
    with pytest.raises(ValueError):
        wire.encode(msg(ident="zz"))
    with pytest.raises(ValueError):
        wire.encode(msg(), max_bytes=10)


@pytest.mark.parametrize("bad", [
    "", "hello", "H3K1", "H3K1|A", "H3K1|Z|abcdef12|s|1|1|-|-|-|", "H3K1|A|ABCDEF12|s|1|1|-|-|-|",
    "H3K1|A|abcdef1|s|1|1|-|-|-|", "H3K1|A|abcdef12|s|1000|1|-|-|-|", "H3K1|A|abcdef12|s|1|101|-|-|-|",
    "H3K1|A|abcdef12|s|-1|1|-|-|-|", "H3K1|A|abcdef12|s|1|1|X|-|-|", "H3K1|A|abcdef12|s|1|1|-|91.0|7.0|",
    "H3K1|A|abcdef12|s|1|1|-|51.0|181|", "H3K1|A|abcdef12|s|1|1|-|51.0|-|", "H3K1|A|abcdef12|s|1|1|-|nan|nan|",
    "H3K1|A|abcdef12|s|١|1|-|-|-|",            # arabisch-indische Ziffer
    "H3K1|A|abcdef12|s|²|1|-|-|-|",            # hochgestellte Zwei: isdigit() wäre True
    "H3K1|A|abcdef12|s|1|1|-|1e2|1e2|", "H3K1|A|abcdef12|s|1|1|-|--1|2|",
])
def test_parse_rejects_malformed(bad):
    assert wire.parse(bad) is None


def test_parse_rejects_oversize_before_looking_at_it():
    assert wire.parse("H3K1|A|abcdef12|s|1|1|-|-|-|" + "x" * wire.RX_MAX_CHARS) is None


def test_trailing_newline_does_not_smuggle_a_second_line():
    m = wire.parse("H3K1|A|abcdef12|s|1|1|-|-|-|ok\nH3K1|A|11111111|evil|9|99|-|-|-|")
    assert m is not None and m.ident == "abcdef12" and "evil" not in m.note


def test_dollar_anchor_newline_is_not_accepted_in_fields():
    assert wire.parse("H3K1|A|abcdef12\n|s|1|1|-|-|-|") is None
    assert wire.parse("H3K1|A|abcdef12|s|1\n|1|-|-|-|") is None


def test_links_and_markup_are_removed():
    m = wire.parse("H3K1|A|abcdef12|http://evil.example/x|1|1|-|-|-|siehe www.evil.com oder t.me/x @alle "
                   "mailto:a@b.de 192.168.0.1 https://x.y")
    assert m is not None
    for bad in ("http", "evil", "www", "t.me", "@", "mailto", "192.168", "x.y"):
        assert bad not in (m.station + " " + m.note), bad


@pytest.mark.parametrize("hide", ["\u202e", "\u200b", "\u2066", "\ufeff", "\u0085", "\x1b", "\x00", "\U000e0041", "\ud800"])
def test_invisible_and_control_characters_are_stripped(hide):
    out = wire.clean_text(f"ex{hide}am{hide}ple", 100)
    assert hide not in out


def test_split_link_cannot_be_reassembled_by_removal():
    # Entfernen kann neue Muster zusammenfügen – das Ergebnis darf nie ein Link sein
    for raw in ["eevil.com.com", "htt" + "p://x.y/ps://a.bc", "a.b" + "\u202e" + ".com", "x" + "www.www.www.a.co" + "m"]:
        out = wire.clean_text(raw, 100)
        assert wire._LINK_RE.search(out) is None, (raw, out)


def test_clean_text_is_idempotent_under_fuzz():
    rnd = random.Random(7)
    alphabet = string.ascii_letters + string.digits + ".:/@| \u202e\u200b\n\t-_äö"
    for _ in range(3000):
        raw = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 120)))
        once = wire.clean_text(raw, 60)
        assert wire.clean_text(once, 60) == once, raw
        assert "|" not in once and "@" not in once and len(once.encode()) <= 60


def test_link_regex_runs_in_linear_time():
    import time
    for payload in ["a." * 4000, "a-" * 4000, "http" + "s" * 4000, "a" * 5000 + ".", ("a." * 60 + "!") * 50]:
        t = time.perf_counter()
        wire.clean_text(payload[:wire.RX_MAX_CHARS * 8], 60)
        assert time.perf_counter() - t < 0.5


def test_parse_fuzz_never_raises_and_only_returns_clean_messages():
    rnd = random.Random(11)
    alphabet = "H3K1|AUTR0123456789abcdef.-:/@ \u202e\n\x00äß\u0663"
    for _ in range(20000):
        n = rnd.randint(0, 80)
        text = "".join(rnd.choice(alphabet) for _ in range(n))
        if rnd.random() < 0.5:
            text = "H3K1|" + text
        m = wire.parse(text)
        if m is not None:
            assert m.typ in wire.TYPES and len(m.ident) == 8 and 0 <= m.count <= 999 and 0 <= m.conf <= 100
            assert "|" not in m.station + m.note and "\n" not in m.station + m.note
            assert wire.parse(wire.encode(m, 400)) is not None


def test_receipt_roundtrip():
    r = wire.receipt("abcdef12", "Stand 2")
    p = wire.parse(wire.encode(r))
    assert p.typ == "R" and p.ident == "abcdef12" and p.station == "Stand 2"
