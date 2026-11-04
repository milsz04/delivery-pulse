FROM apache/superset:5.0.0

USER root

RUN . /app/.venv/bin/activate && uv pip install psycopg2-binary

COPY superset_config.py /app/superset_config.py
COPY bootstrap.sh export_dashboards.sh /app/
RUN sed -i 's/\r$//' /app/bootstrap.sh /app/export_dashboards.sh \
    && chmod +x /app/bootstrap.sh /app/export_dashboards.sh

ENV SUPERSET_CONFIG_PATH=/app/superset_config.py

USER superset

CMD ["/app/bootstrap.sh"]
