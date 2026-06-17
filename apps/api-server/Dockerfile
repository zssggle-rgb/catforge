FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY apps/api-server/pyproject.toml ./pyproject.toml
COPY apps/api-server/alembic.ini ./alembic.ini
COPY apps/api-server/alembic ./alembic
COPY apps/api-server/app ./app
COPY examples ./examples

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
