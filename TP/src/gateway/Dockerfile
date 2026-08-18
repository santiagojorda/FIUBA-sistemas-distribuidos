FROM python:3-alpine

RUN pip3 install pika

WORKDIR /app
ENV PYTHONPATH=/app

COPY common ./common
COPY gateway ./gateway

ENTRYPOINT ["python3", "gateway/gateway.py"]
