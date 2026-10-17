FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-telegram.txt ./requirements-telegram.txt
RUN python -m pip install --no-cache-dir -r requirements-telegram.txt

COPY config.py main.py ./
COPY agent/ ./agent/
COPY tools/ ./tools/

RUN useradd --create-home --shell /usr/sbin/nologin jenefar \
    && mkdir -p /app/data/scratchpad /app/data/skills \
    && chown -R jenefar:jenefar /app

USER jenefar

CMD ["python", "main.py"]
