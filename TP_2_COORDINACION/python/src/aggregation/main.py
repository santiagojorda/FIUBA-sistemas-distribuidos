import os
import logging
import signal

from common import middleware, message_protocol, fruit_item, exceptions

ID = int(os.environ["ID"])
MOM_HOST = os.environ["MOM_HOST"]
OUTPUT_QUEUE = os.environ["OUTPUT_QUEUE"]
SUM_AMOUNT = int(os.environ["SUM_AMOUNT"])
SUM_PREFIX = os.environ["SUM_PREFIX"]
AGGREGATION_AMOUNT = int(os.environ["AGGREGATION_AMOUNT"])
AGGREGATION_PREFIX = os.environ["AGGREGATION_PREFIX"]
AGGREGATION_CONTROL_EXCHANGE = f"{AGGREGATION_PREFIX}_CONTROL_EXCHANGE"
AGGREGATION_CONTROL_QUEUE = f"{AGGREGATION_PREFIX}_CONTROL_QUEUE"
AGGREGATION_EXCHANGE = f"{AGGREGATION_PREFIX}_EXCHANGE"
JOIN_EXCHANGE = "JOIN_EXCHANGE"
TOP_SIZE = int(os.environ["TOP_SIZE"])

AMOUNT_FIELDS_DATA = 3

class AggregationFilter:

    def __init__(self):
        logging.info(f"Aggregation ID: {ID} | Starting aggregation filter")

        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

        self.eof_received_by_client = {}
        self.totals_by_client = {}
        self.finished_clients = set()
        self.input_queue = middleware.DirectQueueRabbitMQ(MOM_HOST, f"{AGGREGATION_PREFIX}-{ID}", AGGREGATION_EXCHANGE)
        self.output_exchange = middleware.DefaultExchangeRabbitMQ(MOM_HOST)

    def handle_exit(self, signum, frame):
        logging.info(f"Aggregation ID: {ID} | Shutdown signal received ({signum}).")
        raise exceptions.GracefulExit()

    def _process_data(self, client_id, fruit, amount):
           
        if client_id not in self.totals_by_client:
            # Es el primer mensaje del cliente, inicializamos sin llorar
            self.totals_by_client[client_id] = {} 

        client_data = self.totals_by_client[client_id]
        current_item = client_data.get(fruit, fruit_item.FruitItem(fruit, 0))
        client_data[fruit] = current_item + fruit_item.FruitItem(fruit, int(amount))
    def _process_eof(self, client_id):
        self.eof_received_by_client[client_id] = self.eof_received_by_client.get(client_id, 0) + 1
        current_eofs = self.eof_received_by_client[client_id]
        
        logging.info(f"Aggregation ID: {ID} | client: {client_id} | Received EOF ({current_eofs}/{SUM_AMOUNT})")

        if current_eofs == SUM_AMOUNT:
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | All EOFs received. Calculating Top.")
            
            client_data = self.totals_by_client.get(client_id, {})
            sorted_fruits = sorted(
                client_data.values(), 
                key=lambda x: x.amount, 
                reverse=True
            )
            
            fruit_top_serialized = [(item.fruit, item.amount) for item in sorted_fruits[:TOP_SIZE]]
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | FINAL TOP: {fruit_top_serialized}")
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | Sending top to join")
            self.output_exchange.send(
                message_protocol.internal.serialize([client_id, fruit_top_serialized]),
                OUTPUT_QUEUE,
            )
            
            self.eof_received_by_client.pop(client_id, None)
            self.totals_by_client.pop(client_id, None)
            self.finished_clients.add(client_id)
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | Cleaned up internal state for client")

    def process_messsage(self, message, ack, nack):
        fields = message_protocol.internal.deserialize(message)
        if isinstance(fields, list) and len(fields) == AMOUNT_FIELDS_DATA:
            client_id, fruit, amount = fields
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | Processing data message")
            self._process_data(client_id, fruit, amount)
        else:
            (client_id,) = message_protocol.internal.deserialize_control(message)
            logging.info(f"Aggregation ID: {ID} | client: {client_id} | Processing EOF message")
            self._process_eof(client_id)
        ack()

    def start(self):
        try:   
            logging.info(f"Aggregation ID: {ID} | Starting to consume...")
            self.input_queue.start_consuming(self.process_messsage)
        except exceptions.GracefulExit:
            logging.info(f"Aggregation ID: {ID} | Loop interrupted by signal.")
        except Exception as e:
            logging.error(f"Aggregation ID: {ID} | Unexpected error: {e}")
        finally:
            logging.info(f"Aggregation ID: {ID} | Closing connections...")
            self.input_queue.close()
            self.output_exchange.close()
            logging.info(f"Aggregation ID: {ID} | Stopped safely.")
def main():
    logging.basicConfig(level=logging.INFO)
    aggregation_filter = AggregationFilter()
    aggregation_filter.start()
    return 0

if __name__ == "__main__":
    main()
