# HL-Scout: read-only. Mount ./data (state, raw, tape) and provide .env at runtime; nothing secret is baked in.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
VOLUME ["/app/data"]
EXPOSE 8765
CMD ["hlscout", "scheduler"]
