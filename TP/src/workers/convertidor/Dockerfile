FROM python:3-alpine

RUN pip3 install pika requests

WORKDIR /app
ENV PYTHONPATH=/app:/app/base

COPY common ./common
COPY workers/base ./base
COPY workers/convertidor ./ 

ENTRYPOINT ["python3", "convertidor.py"]