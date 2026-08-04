# Python builder
FROM python:3.14.0-slim AS builder
WORKDIR /app
COPY requirements.txt .
# Install build dependencies required to compile native wheels such as psycopg2
# Keep these in the builder stage so the runtime image stays small
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
	 build-essential \
	 gcc \
	 python3-dev \
	 libffi-dev \
	 libssl-dev \
 && rm -rf /var/lib/apt/lists/*
# Create a virtual environment and use it for installing Python deps
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ARG DJANGO_SECRET_KEY=CHANGE_ME_TO_A_RANDOM_DEFAULT_SECRET_KEY
ENV DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY

RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --no-input --settings SIEMatic.settings.web

# Runtime
FROM python:3.14.0-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -m appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /app /app
RUN mkdir -p /app/logs \
 && chown -R appuser:appuser /app
RUN chown -R appuser:appuser /opt/venv
USER appuser
EXPOSE 8000
CMD ["python", "manage.py", "serve", "--host", "0.0.0.0","--port", "8000"]
