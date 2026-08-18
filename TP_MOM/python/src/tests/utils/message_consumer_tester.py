class MessageConsumerTester():
	def __init__(self, consumer, message_set, messages_before_close):
		self.consumer = consumer
		self.message_set = message_set
		self.messages_before_close = messages_before_close

	def callback(self, message, ack, nack):
		self.message_set.add(message)
		self.messages_before_close -= 1
		ack()
		if (self.messages_before_close <= 0):
			self.consumer.stop_consuming()
