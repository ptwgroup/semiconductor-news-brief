FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 semibrief
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY config ./config
RUN mkdir -p /data/briefs && chown -R semibrief:semibrief /data

USER semibrief
VOLUME ["/data"]
ENTRYPOINT ["semibrief"]
CMD ["health"]

