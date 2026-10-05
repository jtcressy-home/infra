FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir /data && chown 10001:10001 /data
COPY --chown=10001:10001 src/ ./
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "incident_adapter.server"]
