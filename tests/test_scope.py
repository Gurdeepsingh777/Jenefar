from jenefar.execution.scope import ScopePolicy

def test_exact_host_scope():
    policy = ScopePolicy(["lab.example.com"])
    assert policy.allows("https://lab.example.com/login")
    assert not policy.allows("https://other.example.com")

def test_cidr_scope():
    policy = ScopePolicy(["192.168.1.0/24"])
    assert policy.allows("192.168.1.20")
    assert not policy.allows("192.168.2.20")

def test_empty_scope_denies():
    assert not ScopePolicy([]).allows("127.0.0.1")


def test_cidr_target_is_checked_as_a_full_network():
    policy = ScopePolicy(["192.168.29.0/24"])
    assert policy.allows("192.168.29.0/24")
    assert policy.allows("192.168.29.64/26")
    assert policy.allows("192.168.29.17")
    assert not policy.allows("192.168.28.0/24")
    assert not policy.allows("192.168.0.0/16")


def test_authorized_network_accepts_url_host_and_rejects_out_of_scope_host():
    policy = ScopePolicy(["192.168.29.0/24"])
    assert policy.allows("http://192.168.29.10:8080/login")
    assert not policy.allows("http://192.168.30.10:8080/login")


def test_exact_host_does_not_authorize_entire_cidr():
    policy = ScopePolicy(["192.168.29.10"])
    assert policy.allows("192.168.29.10")
    assert not policy.allows("192.168.29.0/24")
