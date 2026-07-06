from scripts.staging_helpers import normalize_staging_target


def test_normalize_staging_target_defaults_bare_hostname_to_https():
    target = normalize_staging_target("example.com")

    assert target.host == "example.com"
    assert target.port == 443
    assert target.url == "https://example.com"


def test_normalize_staging_target_accepts_full_url():
    target = normalize_staging_target("https://example.com/dashboard?tab=runs")

    assert target.host == "example.com"
    assert target.port == 443
    assert target.url == "https://example.com/dashboard?tab=runs"


def test_normalize_staging_target_preserves_explicit_port():
    target = normalize_staging_target("http://localhost:8080")

    assert target.host == "localhost"
    assert target.port == 8080
    assert target.url == "http://localhost:8080"
