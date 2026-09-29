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
