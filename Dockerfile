FROM python:3.12.9-slim
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 120 --retries 8 -r requirements.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps --no-build-isolation .
COPY migrations ./migrations
COPY sql ./sql
COPY fixtures ./fixtures
COPY tests ./tests
CMD ["iris", "run"]
