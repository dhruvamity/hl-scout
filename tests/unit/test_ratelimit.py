

from hlscout.clients.ratelimit import RateLimiter


class FakeTime:
    def __init__(self):
        self.t = 0.0
        self.spent = []

    def clock(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make(ft, **kw):
    return RateLimiter(clock=ft.clock, sleep=ft.sleep, **kw)


async def test_never_exceeds_budget_under_load():
    ft = FakeTime()
    rl = make(ft)
    start = ft.t
    total = 0
    for _ in range(600):  # 600 x weight 20 = 12,000 weight
        await rl.acquire(20, "deep_vet")
        total += 20
    elapsed_min = (ft.t - start) / 60
    # allowed: initial burst (capacity) + refill; never more than cap/min sustained
    assert total <= rl.capacity + 1080 * elapsed_min + 1e-6


async def test_429_pauses_and_backs_off():
    ft = FakeTime()
    rl = make(ft)
    p1 = rl.on_429()
    p2 = rl.on_429()
    assert p2 > p1 * 1.5
    t0 = ft.t
    await rl.acquire(2, "monitor")
    assert ft.t - t0 >= p2 - 1e-6
    rl.on_success()
    assert rl._backoff == 1.0


async def test_monitor_lane_reserved_over_backfill():
    ft = FakeTime()
    rl = make(ft)
    rl.level = rl.capacity * 0.5  # below backfill/light floors
    t0 = ft.t
    await rl.acquire(20, "monitor")
    assert ft.t == t0  # monitor served immediately
    await rl.acquire(20, "backfill")
    assert ft.t > t0  # backfill had to wait for refill


async def test_surcharge_debit_delays_next_call():
    ft = FakeTime()
    rl = make(ft)
    rl.level = 30
    rl.debit(100)
    t0 = ft.t
    await rl.acquire(20, "monitor")
    assert ft.t > t0
