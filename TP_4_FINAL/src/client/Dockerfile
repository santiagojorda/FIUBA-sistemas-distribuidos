FROM python:3-alpine
RUN pip3 install pika

WORKDIR /app
ENV PYTHONPATH=/app

COPY common ./common
COPY client ./client

ENTRYPOINT ["python3", "client/client.py"]
