from drafter.riot.ratelimit import RateLimiter, parse_limits


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_parse_limits():
    assert parse_limits("20:1,100:120") == [(20, 1.0), (100, 120.0)]


def test_short_window_blocks_then_frees():
    clock = FakeClock()
    rl = RateLimiter("2:1,100:120", clock=clock)
    rl.record()
    rl.record()
    assert rl.wait_time() > 0.9
    clock.t = 1.01
    assert rl.wait_time() == 0


def test_long_window_dominates():
    clock = FakeClock()
    rl = RateLimiter("100:1,3:120", clock=clock)
    for _ in range(3):
        rl.record()
    clock.t = 5
    assert rl.wait_time() > 114


def test_update_keeps_history():
    clock = FakeClock()
    rl = RateLimiter("10:1", clock=clock)
    for _ in range(3):
        rl.record()
    rl.update("3:1,50:10")
    assert rl.wait_time() > 0
