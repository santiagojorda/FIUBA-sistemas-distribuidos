import os
import logging
import signal

from common import middleware, message_protocol, exceptions

MOM_HOST = os.environ["MOM_HOST"]
INPUT_QUEUE = os.environ["INPUT_QUEUE"]
OUTPUT_QUEUE = os.environ["OUTPUT_QUEUE"]
AGGREGATION_AMOUNT = int(os.environ["AGGREGATION_AMOUNT"])
TOP_SIZE = int(os.environ["TOP_SIZE"])

class JoinFilter:
    def __init__(self):
        logging.info("Starting join filter")

        self.eof_received_by_client = {}
        self.fruit_top_by_client = {}

        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

        self.input_queue = middleware.MessageMiddlewareQueueRabbitMQ(MOM_HOST, INPUT_QUEUE)
        self.output_queue = middleware.MessageMiddlewareQueueRabbitMQ(MOM_HOST, OUTPUT_QUEUE)

    def handle_exit(self, signum, frame):
        logging.info(f"Join | Shutdown signal received ({signum}).")
        raise exceptions.GracefulExit()

    def process_messsage(self, message, ack, nack):
        payload = message_protocol.internal.deserialize(message)
        
        client_id = payload[0]
        local_top = payload[1]

        logging.info(f"Join | Received local top | client: {client_id} | top: {local_top}")
        logging.info(f"Join | Estado Cliente {client_id}: {self.eof_received_by_client.get(client_id, 0)}/{AGGREGATION_AMOUNT} tops recibidos")
        if client_id not in self.fruit_top_by_client:
            self.fruit_top_by_client[client_id] = {}
            self.eof_received_by_client[client_id] = 0

        for fruit, amount in local_top:
            current_amount = self.fruit_top_by_client[client_id].get(fruit, 0)
            self.fruit_top_by_client[client_id][fruit] = current_amount + amount

        self.eof_received_by_client[client_id] += 1

        if self.eof_received_by_client[client_id] == AGGREGATION_AMOUNT:
            logging.info(f"Join | BARRERA CUMPLIDA para cliente {client_id}. Despachando al Gateway.")
            global_top_dict = self.fruit_top_by_client[client_id]
            sorted_global = sorted(
                global_top_dict.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            final_top = sorted_global[:TOP_SIZE]
            
            logging.info(f"Join | Sending FINAL GLOBAL TOP | client: {client_id} | top: {final_top}")

            self.output_queue.send(
                message_protocol.internal.serialize([client_id, final_top])
            )
            
            del self.fruit_top_by_client[client_id]
            del self.eof_received_by_client[client_id]

        ack()

    def start(self):
        try:
            logging.info("Join | Starting to consume messages")
            self.input_queue.start_consuming(self.process_messsage)
        except exceptions.GracefulExit:
            logging.info("Join | Loop interrupted by signal.")
        except Exception as e:
            logging.error(f"Join | Unexpected error: {e}")
        finally:
            logging.info("Join | Closing connections...")
            self.input_queue.close()
            self.output_queue.close()
            logging.info("Join | Stopped safely.")
def main():
    logging.basicConfig(level=logging.INFO)
    join_filter = JoinFilter()
    join_filter.start()
    return 0

if __name__ == "__main__":
    main()