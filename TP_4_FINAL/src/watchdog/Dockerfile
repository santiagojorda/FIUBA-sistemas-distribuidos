FROM python:3-alpine

RUN pip3 install pika

WORKDIR /app
ENV PYTHONPATH=/app

COPY common ./common
COPY watchdog ./watchdog

ENTRYPOINT ["python3", "watchdog/watchdog.py"]
