import os
import logging
import threading
import signal
from common import middleware, message_protocol, fruit_item, exceptions

ID = int(os.environ["ID"])
MOM_HOST = os.environ["MOM_HOST"]
INPUT_QUEUE = os.environ["INPUT_QUEUE"]
SUM_AMOUNT = int(os.environ["SUM_AMOUNT"])
SUM_PREFIX = os.environ["SUM_PREFIX"]
SUM_CONTROL_EXCHANGE = "SUM_CONTROL_EXCHANGE"
SUM_CONTROL_QUEUE = "SUM_CONTROL_QUEUE"
AGGREGATION_AMOUNT = int(os.environ["AGGREGATION_AMOUNT"])
AGGREGATION_PREFIX = os.environ["AGGREGATION_PREFIX"]
AGGREGATION_EXCHANGE = f"{AGGREGATION_PREFIX}_EXCHANGE"

COUNT_OF_FIELDS_IN_DATA_MESSAGE = 3
AMOUNT_OF_LETTERS_IN_ALPHABET = 25
TIME_TO_WAIT_FOR_RESIDUAL_DATA = 5

class SumFilter:
    def __init__(self):
        
        logging.info(f"Starting sum filter with ID {ID}")
        
        self.eof_received_by_client = {}
        self.condition = threading.Condition()
        self.amount_by_fruit_by_client = {}

        self.stop_event = threading.Event()

        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

        self.input_queue = middleware.DirectQueueRabbitMQ(MOM_HOST, INPUT_QUEUE)
        self.control_exchange = middleware.FanoutExchangeRabbitMQ(MOM_HOST, SUM_CONTROL_EXCHANGE)
        self.control_queue = middleware.FanoutQueueRabbitMQ(MOM_HOST, f"{SUM_CONTROL_QUEUE}-{ID}", SUM_CONTROL_EXCHANGE)
        self.data_output_exchange = middleware.DirectExchangeRabbitMQ(MOM_HOST,AGGREGATION_EXCHANGE)

    def handle_exit(self, signum, frame):
        logging.info(f"Sum ID: {ID} | Shutdown signal ({signum}) received. Closing connections...")
        raise exceptions.GracefulExit()



    # procesa de la exchange de control
    def _run_control_polling(self):
        logging.info(f"Sum ID: {ID} | Starting control polling thread")
        try:
            self.control_queue.start_consuming(self.process_control_message)
        except Exception as e:
            if not self.stop_event.is_set():
                logging.error(f"Error in control polling: {e}")

    def process_control_message(self, message, ack, nack):
        if self.stop_event.is_set():
            logging.info(f"Sum ID: {ID} | Control Thread | Stop event set. Not processing control message.")
            nack(requeue=True)
            return

        (client_id,) = message_protocol.internal.deserialize_control(message)
        self._process_control_eof(client_id)
        ack()

    def get_aggregator_shard(self, fruit_name):
      if not fruit_name:
              return 0

      first_letter = fruit_name.lower()[0]
      letter_index = ord(first_letter) - ord('a')
      if not (0 <= letter_index <= AMOUNT_OF_LETTERS_IN_ALPHABET):
          return 0
      return letter_index % AGGREGATION_AMOUNT

    def _process_control_eof(self, client_id):
        with self.condition:
            self.eof_received_by_client[client_id] = True
            logging.info(f"Sum ID: {ID} | Control Thread | client: {client_id} | Waiting residual data from message queue...")
            self.condition.wait(timeout=TIME_TO_WAIT_FOR_RESIDUAL_DATA)

            if self.stop_event.is_set():
                logging.info(f"Sum ID: {ID} | Control Thread | client: {client_id} | Shutdown event set while waiting for residual data. Not forwarding to aggregators.")
                return

            amount_by_fruit = self.amount_by_fruit_by_client.get(client_id, {})
            self.eof_received_by_client.pop(client_id, None)

        logging.info(f"Sum ID: {ID} | Control Thread | client: {client_id} | Forwarding data to aggregators. Fruits")
        for final_fruit_item in amount_by_fruit.values():
            shard_id = self.get_aggregator_shard(final_fruit_item.fruit)
            routing_key = f"{AGGREGATION_PREFIX}-{shard_id}"
            self.data_output_exchange.send(
                message_protocol.internal.serialize([client_id, final_fruit_item.fruit, final_fruit_item.amount]),
                routing_key
            )

        for aggregation_id in range(AGGREGATION_AMOUNT):
            routing_key = f"{AGGREGATION_PREFIX}-{aggregation_id}"
            self.data_output_exchange.send(message_protocol.internal.serialize_control(client_id), routing_key)
        logging.info(f"Sum ID: {ID} | Control Thread | client: {client_id} | Cleaned up internal state for client.")
        self.amount_by_fruit_by_client.pop(client_id, None)
        
    # procesa de la queue de ingreso  
    def process_data_messsage(self, message, ack, nack):
        fields = message_protocol.internal.deserialize(message)
        if len(fields) == COUNT_OF_FIELDS_IN_DATA_MESSAGE:
            with self.condition:
                client_id, fruit, amount = fields
                logging.info(f"Sum ID: {ID} | Data Thread | client: {client_id} | fruit: {fruit} | amount: {amount}")
                is_eof = self._process_data(*fields)
                if is_eof:
                    logging.info(f"Sum ID: {ID} | Data Thread | client: {client_id} | Condition EOF received in data message. Forwarding to control exchange.")
                    self.condition.notify_all()
        else:
            self._send_eof_to_control_exchange(fields[0])

        ack()

    def _send_eof_to_control_exchange(self, client_id):
          client_id = int(client_id)
          logging.info(f"Sum ID: {ID} | Data Thread | client: {client_id} | EOF")
          self.control_exchange.send(message_protocol.internal.serialize_control(client_id))
          logging.info(f"Sum ID: {ID} | Data Thread | Control exchange | client: {client_id} | Forwarding EOF")

    def _process_data(self, client_id, fruit, amount):
            amount_by_fruit = self.amount_by_fruit_by_client.setdefault(client_id, {})
            amount_by_fruit[fruit] = amount_by_fruit.get(
                fruit, fruit_item.FruitItem(fruit, 0)
            ) + fruit_item.FruitItem(fruit, int(amount))
        
            if self.eof_received_by_client.get(client_id, False):
                return True
            return False

    def start(self):
        control_thread = threading.Thread(
            target=self._run_control_polling,
            name=f"sum-control-polling-{ID}",
            daemon=False,
        )
        control_thread.start()

        try:
            self.input_queue.start_consuming(self.process_data_messsage)
        except (KeyboardInterrupt, SystemExit):
            logging.info(f"Sum ID: {ID} | SIGINT capturado (KeyboardInterrupt).")
        except Exception as e:
            logging.error(f"Sum ID: {ID} | Error: {e}")
        finally:
            self.stop_event.set()
            with self.condition:
                self.condition.notify_all()
            
            logging.info(f"Sum ID: {ID} | Stopping control thread...")
            self.control_queue.stop_consuming()
            control_thread.join()


            logging.info(f"Sum ID: {ID} | Closing connections..")
            control_thread.join()
            self.input_queue.close()
            self.control_queue.close()
            self.control_exchange.close()
            self.data_output_exchange.close()
            logging.info(f"Sum ID: {ID} | Filter stopped safely.")

def main():
    logging.basicConfig(level=logging.INFO)
    sum_filter = SumFilter()
    sum_filter.start()
    return 0


if __name__ == "__main__":
    main()
