# Python builder
FROM python:3.13.7-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --no-input

# Runtime
FROM python:3.13.7-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -m appuser
WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app
RUN mkdir -p /app/log \
 && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "manage.py", "serve", "0.0.0.0:8000"]