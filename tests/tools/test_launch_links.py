import pathlib
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import launch_links as ll  # noqa: E402


def test_build_utm_url_adds_all_params():
    url = ll.build_utm_url("https://example.com/", "hn", "referral",
                           "launch", "show-hn")
    q = parse_qs(urlsplit(url).query)
    assert q["utm_source"] == ["hn"]
    assert q["utm_medium"] == ["referral"]
    assert q["utm_campaign"] == ["launch"]
    assert q["utm_content"] == ["show-hn"]


def test_build_utm_url_preserves_existing_query():
    url = ll.build_utm_url("https://example.com/?ref=x", "hn",
                           "referral", "launch")
    q = parse_qs(urlsplit(url).query)
    assert q["ref"] == ["x"]
    assert q["utm_source"] == ["hn"]


def test_canonical_links_covers_every_channel():
    links = ll.canonical_links("https://example.com/")
    assert set(links) == set(ll.CHANNELS)
    for url in links.values():
        assert "utm_source=" in url and "utm_campaign=" in url


def test_render_manifest_is_generated_and_sorted():
    md = ll.render_manifest({"b": "https://b", "a": "https://a"})
    assert "GENERATED" in md
    assert md.index("`a`") < md.index("`b`")
