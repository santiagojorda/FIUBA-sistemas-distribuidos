FROM python:3-alpine

RUN pip3 install pika

WORKDIR /app
ENV PYTHONPATH=/app:/app/base

COPY common ./common
COPY workers/base ./base
COPY workers/bank_shard ./

ENTRYPOINT ["python3", "agregador_bancario.py"]