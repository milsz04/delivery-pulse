FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pytest.ini .
COPY pulse ./pulse
COPY tests ./tests

RUN useradd --create-home pulse && mkdir -p /app/reports && chown pulse /app/reports
USER pulse

CMD ["uvicorn", "pulse.api:app", "--host", "0.0.0.0", "--port", "8000"]
