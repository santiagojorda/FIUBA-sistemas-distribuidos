FROM python:3-alpine

RUN pip3 install pika

WORKDIR /app
ENV PYTHONPATH=/app:/app/base

COPY common ./common
COPY workers/base ./base
COPY workers/contador_distinto ./

ENTRYPOINT ["python3", "contador_distinto.py"]
