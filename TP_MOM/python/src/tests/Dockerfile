FROM python:3-alpine

COPY tests/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY common ./common
COPY tests .

ENTRYPOINT ["pytest", "-x"]
