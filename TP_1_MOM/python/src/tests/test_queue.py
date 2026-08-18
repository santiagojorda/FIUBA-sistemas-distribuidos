import os
import pytest
import multiprocessing

from common.middleware import middleware_rabbitmq
from utils.message_consumer_tester import MessageConsumerTester

TEST_QUEUE_NAME = "test_queue"

MOM_HOST = os.environ['MOM_HOST']

# -----------------------------------------------------------------------------
# HELP FUNCTIONS
# -----------------------------------------------------------------------------

def _message_set_consumer(message_set, messages_before_close):
	consumer_queue = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, TEST_QUEUE_NAME)
	message_consumer_tester = MessageConsumerTester(consumer_queue, message_set, messages_before_close)
	consumer_queue.start_consuming(lambda message, ack, nack: message_consumer_tester.callback(message, ack, nack))

def _generate_messages(amount):
	return list(map(lambda n: bytes(f"{n}", "utf-8"), range(amount)))

def _test_queue(producer_amount, consumer_amount, message_amount):
	messages = _generate_messages(message_amount)

	with multiprocessing.Manager() as manager:
		#Introduced in Python 3.14. Ref: docs.python.org/3/library/multiprocessing.html#multiprocessing.managers.SyncManager.set
		message_set = manager.set()

		producer_queues = []
		for _ in range(producer_amount):
			producer_queue = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, TEST_QUEUE_NAME)
			producer_queues.append(producer_queue)
			
		consummer_processes = []
		for i in range(consumer_amount):
			messages_before_close = len(messages) // consumer_amount
			if (i == 0):
				messages_before_close += len(messages) % consumer_amount
			consummer_process = multiprocessing.Process(target=_message_set_consumer, args=(message_set, messages_before_close))
			consummer_process.start()
			consummer_processes.append(consummer_process)

		for i in range(len(messages)):
			producer_queues[i % producer_amount].send(messages[i])

		for consummer_process in consummer_processes:
			consummer_process.join()

		for producer_queue in producer_queues:
			producer_queue.close()

		assert len(message_set) == len(messages), "The amount of consummed messages is not as expected"
		for message in messages:
			assert message in message_set, f"The message {message} was not consummed"

# -----------------------------------------------------------------------------
# GENERAL TESTS
# -----------------------------------------------------------------------------

def test_init_and_close():
	queue = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, TEST_QUEUE_NAME)
	queue.close()

def test_listen_to_message_and_close():
	message = b"message"
	message_set = set()
	queue = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, TEST_QUEUE_NAME)
	queue.send(message)
	message_consumer_tester = MessageConsumerTester(queue, message_set, 1)
	queue.start_consuming(lambda message, ack, nack: message_consumer_tester.callback(message, ack, nack))

	assert len(message_set) == 1, "The amount of consummed messages is not as expected"
	assert message in message_set, f"The message {message} was not consummed"

def _test_messages_dont_mix_between_queues(queue_name, queue, messages):
	message_set = set()
	message_consumer_tester = MessageConsumerTester(queue, message_set, len(messages))
	
	queue.start_consuming(lambda message, ack, nack: message_consumer_tester.callback(message, ack, nack))

	assert len(message_set) == len(messages), f"The amount of consummed messages is not as expected in {queue_name}"
	for message in messages:
		assert message in message_set, f"The message {message} was not consummed from {queue_name}"

def test_messages_dont_mix_between_queues():
	messages = _generate_messages(8)
	messages_a = messages[:4]
	messages_b = messages[4:]
	test_queue_name_2 = f"{TEST_QUEUE_NAME}_2"

	queue_a = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, TEST_QUEUE_NAME)
	queue_b = middleware_rabbitmq.MessageMiddlewareQueueRabbitMQ(MOM_HOST, test_queue_name_2)

	for message in messages_a:
		queue_a.send(message)

	for message in messages_b:
		queue_b.send(message)

	_test_messages_dont_mix_between_queues(TEST_QUEUE_NAME, queue_a, messages_a)
	_test_messages_dont_mix_between_queues(test_queue_name_2, queue_b, messages_b)

# -----------------------------------------------------------------------------
#  PRODUCER CONSUMER TESTS
# -----------------------------------------------------------------------------

def test_one_producer_one_consumer_one_message():
	_test_queue(1, 1, 1)

def test_one_producer_one_consumer_some_messages():
	_test_queue(1, 1, 3)

def test_one_producer_one_consumer_many_messages():
	_test_queue(1, 1, 13)

def test_one_producer_many_consumers_some_messages():
	_test_queue(1, 3, 3)

def test_one_producer_many_consumers_many_messages():
	_test_queue(1, 3, 13)

def test_many_producers_one_consumer_one_message():
	_test_queue(3, 1, 1)

def test_many_producers_one_consumer_some_messages():
	_test_queue(3, 1, 3)

def test_many_producers_one_consumer_many_messages():
	_test_queue(3, 1, 13)

def test_many_producers_many_consumers_some_messages():
	_test_queue(3, 3, 3)

def test_many_producers_many_consumers_many_messages():
	_test_queue(3, 3, 13)
