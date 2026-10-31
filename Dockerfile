FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY errand ./errand
RUN pip install --no-cache-dir .
ENV ERRAND_DB=/data/errand.db
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "errand serve --host 0.0.0.0 --port ${PORT:-8000}"]
