# syntax=docker/dockerfile:1
FROM rust:1.96-bookworm AS builder
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
COPY backend/ ./
COPY migrations/ /app/migrations/
ENV SQLX_OFFLINE=true
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/app/backend/target \
    cargo build --locked --release -p api-server -j 2 && cp target/release/api-server /api-server

FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 curl \
    && rm -rf /var/lib/apt/lists/* && useradd --system --uid 10001 app
WORKDIR /app
COPY --from=builder /api-server /usr/local/bin/api-server
USER app
ENV HOST=0.0.0.0 PORT=3000
EXPOSE 3000
CMD ["api-server"]
