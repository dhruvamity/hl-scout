import httpx
import pytest

from hlscout.clients.info import InfoClient
from hlscout.clients.ratelimit import RateLimiter


async def test_429_then_success_and_surcharge():
    calls = {"n": 0}

    def handler(req: httpx.Request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[{"x": i} for i in range(100)])

    t = [0.0]

    async def sleep(s):
        t[0] += s

    rl = RateLimiter(sleep=sleep, clock=lambda: t[0])
    c = InfoClient(rl, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    data = await c.post({"type": "userFillsByTime", "user": "0x0"})
    assert len(data) == 100 and calls["n"] == 2 and len(rl.pauses) == 1
    assert rl.level < rl.capacity - 20  # spent despite refill during the pause


def test_host_allowlist():
    with pytest.raises(ValueError):
        InfoClient(RateLimiter(), url="https://evil.example.com/info")
