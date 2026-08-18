FROM python:3-alpine

RUN pip3 install pika

COPY common ./common
COPY sum .

ENTRYPOINT ["python3", "main.py"]
