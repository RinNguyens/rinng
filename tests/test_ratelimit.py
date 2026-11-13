from rinng.exchanges.ratelimit import WeightLimiter, WindowLimiter


class FakeTime:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_weight_limiter_passes_under_budget():
    t = FakeTime()
    limiter = WeightLimiter(2400, clock=t.clock, sleep=t.sleep)
    limiter.update(1199)
    limiter.acquire()
    assert t.slept == []


def test_weight_limiter_waits_for_next_minute_at_budget():
    t = FakeTime(now=130.0)  # 10 giây sau đầu phút
    limiter = WeightLimiter(2400, clock=t.clock, sleep=t.sleep)
    limiter.update(1200)
    limiter.acquire()
    assert t.slept == [50.5]
    limiter.acquire()
    assert len(t.slept) == 1  # bộ đếm đã về 0, không chờ lần nữa


def test_window_limiter_allows_half_then_waits():
    t = FakeTime()
    limiter = WindowLimiter(20, 2.0, clock=t.clock, sleep=t.sleep)
    for _ in range(10):
        limiter.acquire()
    assert t.slept == []
    t.now = 0.5
    limiter.acquire()
    assert t.slept == [1.5]


def test_window_limiter_forgets_old_requests():
    t = FakeTime()
    limiter = WindowLimiter(4, 2.0, clock=t.clock, sleep=t.sleep)
    limiter.acquire()
    limiter.acquire()
    t.now = 2.0
    limiter.acquire()
    assert t.slept == []


def test_window_limiter_capacity_at_least_one():
    assert WindowLimiter(1, 2.0).capacity == 1
