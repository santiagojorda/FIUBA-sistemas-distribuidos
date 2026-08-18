import os
import pytest
import multiprocessing
import time

from common.middleware import middleware_rabbitmq
from utils.message_consumer_tester import MessageConsumerTester
import requests
from requests.auth import HTTPBasicAuth

RABBITMQ_MANAGEMENT_PORT = 15672
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.environ.get("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")

TEST_EXCHANGE_NAME = "test_exchange"

MOM_HOST = os.environ['MOM_HOST']

# -----------------------------------------------------------------------------
# HELP FUNCTIONS
# -----------------------------------------------------------------------------

def _wait_for_queues(routing_keys_by_consumers, timeout=6, poll_interval=0.1):
    """
    Esperar a que todos los "bindings" esperados de las colas al exchange de prueba existan.
    
    ACLARACIÓN: Esta función sincroniza los "bindings" en un contexto en donde:
    - No podemos extender el middleware ni agregarle lógica
    - No podemos asumir la existencia de mecanismos de sincronización en el middleware
    - Agregar lógica adicional de comunicación entre componentes complejizaría los casos de prueba
    
    Si se te presenta un caso que pensás que amerita una solución similar; evalua exhaustivamente que no haya mejores opciones;
    y recordá, este tipo de lógica debería estar en el middleware, que es el componente que abstrae la lógica de comunicación.
    """
    
    bindings_per_key = {}

    for routing_keys in routing_keys_by_consumers.values():
        for key in routing_keys:
            bindings_per_key[key] = bindings_per_key.get(key, 0) + 1

    url = (
        f"http://{MOM_HOST}:{RABBITMQ_MANAGEMENT_PORT}"
        f"/api/exchanges/{requests.utils.quote(RABBITMQ_VHOST, safe='')}"
        f"/{requests.utils.quote(TEST_EXCHANGE_NAME, safe='')}"
        f"/bindings/source"
    )

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            auth = HTTPBasicAuth(RABBITMQ_USER, RABBITMQ_PASS)
            response = requests.get(url, auth= auth, timeout=2)
            response.raise_for_status()
            bindings = response.json()
        except Exception as e:
            # Might fail if the exchange is not declared yet
            time.sleep(poll_interval)
            continue

        actual_bindings = {}

        for binding in bindings:
            if binding.get("destination_type") != "queue":
                continue
            key = binding.get("routing_key")
            if key:
                actual_bindings[key] = actual_bindings.get(key, 0) + 1


        all_ready = True
        for key, expected_count in bindings_per_key.items():
            if actual_bindings.get(key, 0) < expected_count:
                all_ready = False
                break

        if all_ready:
            return

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out waiting for bindings on exchange '{TEST_EXCHANGE_NAME}'. "
        f"Expected: {bindings_per_key}"
    )

def _message_set_consumer(message_set, messages_before_close, routing_keys):
	consumer_exchange = middleware_rabbitmq.MessageMiddlewareExchangeRabbitMQ(MOM_HOST, TEST_EXCHANGE_NAME, routing_keys)
	message_consumer_tester = MessageConsumerTester(consumer_exchange, message_set, messages_before_close)
	consumer_exchange.start_consuming(lambda message, ack, nack: message_consumer_tester.callback(message, ack, nack))

def _test_exchange(routing_keys_by_consumers, messages_by_routing_key):
	with multiprocessing.Manager() as manager:
		consumers = routing_keys_by_consumers.keys()
		message_set_by_consumer = dict()
		consummer_processes = []

		for consumer in consumers:
			messages_before_close = 0
			for consumer_routing_key in routing_keys_by_consumers[consumer]:
				messages_before_close += len(messages_by_routing_key[consumer_routing_key])
			#Introduced in Python 3.14. Ref: docs.python.org/3/library/multiprocessing.html#multiprocessing.managers.SyncManager.set
			message_set_by_consumer[consumer] = manager.set()
			consummer_process = multiprocessing.Process(target=_message_set_consumer, args=(message_set_by_consumer[consumer], messages_before_close, routing_keys_by_consumers[consumer]))
			consummer_process.start()
			consummer_processes.append(consummer_process)

		_wait_for_queues(routing_keys_by_consumers)

		for routing_key, messages in messages_by_routing_key.items():
			producer_exchange = middleware_rabbitmq.MessageMiddlewareExchangeRabbitMQ(MOM_HOST, TEST_EXCHANGE_NAME, [routing_key])
			for message in messages:
				producer_exchange.send(message)
			producer_exchange.close()

		for consummer_process in consummer_processes:
			consummer_process.join()

		for consumer in consumers:
			message_set = message_set_by_consumer[consumer]
			messages = []
			for consumer_routing_key in routing_keys_by_consumers[consumer]:
				messages += messages_by_routing_key[consumer_routing_key]

			assert len(message_set) == len(messages), f"The amount of consummed messages is not as expected for consumer {consumer}"
			for message in messages:
				assert message in message_set, f"The message {message} was not consummed by {consumer}"

# -----------------------------------------------------------------------------
# GENERAL TESTS
# -----------------------------------------------------------------------------

def test_init_and_close():
	routing_keys = ["route_1"]
	exchange = middleware_rabbitmq.MessageMiddlewareExchangeRabbitMQ(MOM_HOST, TEST_EXCHANGE_NAME, routing_keys)
	exchange.close()

# -----------------------------------------------------------------------------
#  DIRECT MESSAGING TESTS
# -----------------------------------------------------------------------------
def test_direct_messaging_one_consumer_one_message():
	_test_exchange({
		"consumer_1": ["route_1"]
		}, {
		"route_1": [b"message"]
		})

def test_direct_messaging_one_consumer_many_messages():
	_test_exchange({
		"consumer_1": ["route_1"]
		}, {
		"route_1": [b"message", b"message_2", b"message_3"]
		})

def test_direct_messaging_many_consumers_many_messages():
	_test_exchange({
		"consumer_1": ["route_1"],
		"consumer_2": ["route_2"],
		"consumer_3": ["route_3"]
		}, {
		"route_1": [b"message_1"],
		"route_2": [b"message_2"],
		"route_3": [b"message_3"]
		})

# -----------------------------------------------------------------------------
#  BROADCAST MESSAGING TESTS
# -----------------------------------------------------------------------------

def test_broadcast_single_routing_key():
	_test_exchange({
		"consumer_1": ["route_1"],
		"consumer_2": ["route_1"],
		"consumer_3": ["route_1"]
		}, {
		"route_1": [b"message_1"],
		})

def test_broadcast_many_routing_keys():
	_test_exchange({
		"consumer_1": ["route_1"],
		"consumer_2": ["route_1", "route_2"],
		"consumer_3": ["route_1", "route_2"],
		}, {
		"route_1": [b"message_1"],
		"route_2": [b"message_2"],
		})