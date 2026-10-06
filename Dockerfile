FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e .
RUN useradd --create-home --uid 10001 jenefar && mkdir -p /app/data && chown -R jenefar:jenefar /app
USER jenefar
EXPOSE 8787
CMD ["python", "-m", "jenefar.production.service"]
