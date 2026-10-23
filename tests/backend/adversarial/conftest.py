def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "coverage_gap: an adversarial expectation no existing rule or summary setting covers",
    )
    config.addinivalue_line(
        "markers", "malformed: a deliberately malformed archive or parser case"
    )
