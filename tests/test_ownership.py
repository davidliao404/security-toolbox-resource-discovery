from resource_discovery.ownership import score_ownership


def test_scores_direct_domain_match_high():
    score = score_ownership(
        row={"host": "vpn.example.org", "domain": "example.org"},
        authorized_scope={"root_domains": ["example.org"]},
    )

    assert score == 0.95


def test_scores_organization_only_match_as_candidate():
    score = score_ownership(
        row={"org": "Example Limited"},
        authorized_scope={"org_names": ["Example Limited"]},
    )

    assert score == 0.7


def test_scores_unrelated_cloud_result_low():
    score = score_ownership(
        row={"host": "random.cloudfront.net", "org": "Amazon.com, Inc."},
        authorized_scope={
            "root_domains": ["example.org"],
            "org_names": ["Example Limited"],
        },
    )

    assert score == 0.3
