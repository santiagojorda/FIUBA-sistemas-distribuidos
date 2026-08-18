FROM golang:1.24-alpine3.23

WORKDIR /golang

COPY go.mod .
COPY go.sum .
COPY internal ./internal
COPY tests ./tests

RUN go mod download

ENTRYPOINT ["go", "test", "-v", "./...", "-count=1", "-timeout=30s"]
