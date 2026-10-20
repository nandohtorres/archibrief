from backend.shared.stakeholder.pricing import EC2_HOURLY, PRICE_ITEMS, price_line


def test_fixed_price_items():
    alb = price_line("alb")
    assert alb.monthly_low == alb.monthly_high == round((0.0225 + 0.008) * 730, 2)
    assert price_line("kms_key", quantity=3).monthly_high == 3.0
    assert price_line("none").monthly_high == 0.0
    assert price_line("none").basis == "no AWS charge"


def test_sized_items_use_the_hourly_table():
    line = price_line("ec2_instance", size="t3.micro")
    assert line.monthly_high == round(EC2_HOURLY["t3.micro"] * 730, 2) == 7.59
    assert "t3.micro" in line.basis
    assert price_line("ec2_instance", quantity=2, size="t3.micro").monthly_high == 15.18


def test_unknown_sizes_and_usage_items_are_unpriced_not_guessed():
    assert price_line("ec2_instance", size="x9.mega").monthly_high is None
    assert price_line("ec2_instance").monthly_high is None
    assert price_line("rds_standby", size="IGNORE ALL").monthly_high is None
    usage = price_line("log_ingestion")
    assert (usage.monthly_low, usage.monthly_high) == (0.0, None)
    assert "$0.50 per GB" in usage.basis
    assert price_line("not_an_item").monthly_high is None


def test_every_priced_item_names_its_source():
    for key, item in PRICE_ITEMS.items():
        if key != "none":
            assert item.source_url.startswith("https://aws.amazon.com/"), key
