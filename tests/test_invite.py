from mulchd.invite import matches_allowed_domains


def test_null_patterns_accepts_any_email():
    assert matches_allowed_domains("alice@anywhere.com", None) is True


def test_empty_list_accepts_any_email():
    assert matches_allowed_domains("alice@anywhere.com", []) is True


def test_exact_domain_match():
    assert matches_allowed_domains("alice@company.com", ["company.com"]) is True


def test_exact_domain_no_match():
    assert matches_allowed_domains("alice@other.com", ["company.com"]) is False


def test_wildcard_single_subdomain():
    assert matches_allowed_domains("alice@ext.company.com", ["*.company.com"]) is True


def test_wildcard_deep_subdomain():
    assert matches_allowed_domains("alice@deep.ext.company.com", ["*.company.com"]) is True


def test_wildcard_does_not_match_bare_domain():
    assert matches_allowed_domains("alice@company.com", ["*.company.com"]) is False


def test_multiple_patterns_first_matches():
    assert matches_allowed_domains("alice@company.com", ["company.com", "*.company.com"]) is True


def test_multiple_patterns_second_matches():
    assert matches_allowed_domains("alice@ext.company.com", ["company.com", "*.company.com"]) is True


def test_multiple_patterns_none_match():
    assert matches_allowed_domains("alice@other.net", ["company.com", "*.company.com"]) is False
