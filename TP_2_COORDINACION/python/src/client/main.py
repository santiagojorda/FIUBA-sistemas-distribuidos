import os
import logging
import csv
import socket
import signal

from common import message_protocol

INPUT_FILE = os.environ["INPUT_FILE"]
OUTPUT_FILE = os.environ["OUTPUT_FILE"]
SERVER_HOST = os.environ["SERVER_HOST"]
SERVER_PORT = int(os.environ["SERVER_PORT"])


class Client:

    def __init__(self):
        self.closed = False
        self._prev_sigterm_handler = signal.signal(signal.SIGTERM, self.handle_sigterm)

    def handle_sigterm(self, signum, frame):
        logging.info("Recieved SIGTERM signal")
        self.closed = True
        self.disconnect()

        if self._prev_sigterm_handler:
            self._prev_sigterm_handler(signum, frame)

    def connect(self, server_host, server_port):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.connect((server_host, server_port))

    def disconnect(self):
        if self.server_socket:
            self.server_socket.shutdown(socket.SHUT_RDWR)

    def send_fruit_records(self, input_file):
        logging.info("Sending fruit records")
        with open(input_file, newline="\n") as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=",", quotechar='"')
            for row in csv_reader:
                [fruit, amount] = row
                message_protocol.external.send_msg(
                    self.server_socket,
                    message_protocol.external.MsgType.FRUIT_RECORD,
                    fruit,
                    int(amount),
                )
                message_protocol.external.recv_msg(self.server_socket)

        message_protocol.external.send_msg(
            self.server_socket, message_protocol.external.MsgType.END_OF_RECODS
        )
        message_protocol.external.recv_msg(self.server_socket)

    def recv_fruit_top(self, output_file):
        logging.info("Receiving fruit top")
        fruit_top_message = message_protocol.external.recv_msg(self.server_socket)
        message_protocol.external.send_msg(
            self.server_socket, message_protocol.external.MsgType.ACK
        )

        if fruit_top_message[0] != message_protocol.external.MsgType.FRUIT_TOP:
            raise TypeError("Expected a FRUIT_TOP message")

        with open(output_file, "w") as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=",", quotechar='"')
            for fruit_item in fruit_top_message[1]:
                csv_writer.writerow(fruit_item)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    client = Client()

    try:
        client.connect(SERVER_HOST, SERVER_PORT)
        client.send_fruit_records(INPUT_FILE)
        client.recv_fruit_top(OUTPUT_FILE)
    except socket.error:
        if not client.closed:
            logging.error("The connection with the server was lost")
            return 1
    except Exception as e:
        logging.error(e)
        return 2
    finally:
        if not client.closed:
            client.disconnect()

    return 0


if __name__ == "__main__":
    main()
