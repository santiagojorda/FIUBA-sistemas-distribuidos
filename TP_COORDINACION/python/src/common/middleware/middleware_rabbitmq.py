import pika
from .rabbitmq_base import RabbitMQBase, handle_pika_errors

MAX_MESSAGES_PER_WORKER = 1
DIRECT_EXCHANGE_TYPE = 'direct'
FANOUT_EXCHANGE_TYPE = 'fanout'

class MessageMiddlewareQueueRabbitMQ(RabbitMQBase):
    def __init__(self, host, queue_name, exchange_name=None, exchange_type=DIRECT_EXCHANGE_TYPE):
        super().__init__(host)
        self.queue_name = queue_name
        self._declare_queue()
        if exchange_name:
            self._declare_exchange(exchange_name, exchange_type)
            self._bind_queue(exchange_name)

    @handle_pika_errors("declarar exchange")
    def _declare_exchange(self, exchange_name, exchange_type):
        self.channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type)

    @handle_pika_errors("bindear la cola")
    def _bind_queue(self, exchange_name):
        self.channel.queue_bind(
            exchange=exchange_name,
            queue=self.queue_name,
            routing_key=self.queue_name
        )

    @handle_pika_errors("declarar la cola")
    def _declare_queue(self):
        self.channel.queue_declare(queue=self.queue_name)
        self.channel.basic_qos(prefetch_count=MAX_MESSAGES_PER_WORKER)

    @handle_pika_errors("enviar a la cola")
    def send(self, message):
        # El default exchange ('') manda directo a la cola que coincida con la routing_key
        self.channel.basic_publish(
            exchange='',
            routing_key=self.queue_name,
            body=message
        )

    @handle_pika_errors("empezar a consumir")
    def start_consuming(self, on_message_callback):
        def internal_callback(ch, method, properties, body):
            on_message_callback(
                body,
                lambda: ch.basic_ack(delivery_tag=method.delivery_tag),
                lambda: ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True),
            )
        internal_callback = internal_callback
        
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=internal_callback,
            auto_ack=False
        )
        self.channel.start_consuming()

    @handle_pika_errors("detener consumo")
    def stop_consuming(self):
        if self.connection and self.connection.is_open:
            self.connection.add_callback_threadsafe(self.channel.stop_consuming)


class MessageMiddlewareExchangeRabbitMQ(RabbitMQBase):
    """Clase base para Exchanges. Hereda lógica de conexión y de publicación."""
    
    def __init__(self, host, exchange_name, exchange_type):
        super().__init__(host)
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self._declare_exchange()

    @handle_pika_errors("declarar exchange")
    def _declare_exchange(self):
        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type=self.exchange_type
        )

    @handle_pika_errors("enviar mensaje")
    def send(self, message, routing_key=""):
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=routing_key,
            body=message
        )

class DefaultExchangeRabbitMQ(RabbitMQBase):    
    def __init__(self, host):
        super().__init__(host)

    @handle_pika_errors("enviar mensaje (default exchange)")
    def send(self, message, routing_key):
        self.channel.basic_publish(
            exchange='',
            routing_key=routing_key,
            body=message
        )

class DirectQueueRabbitMQ(MessageMiddlewareQueueRabbitMQ):
    def __init__(self, host, queue_name, exchange_name=None):
        super().__init__(host, queue_name, exchange_name)

class FanoutQueueRabbitMQ(MessageMiddlewareQueueRabbitMQ):
    def __init__(self, host, queue_name, exchange_name=None):
        super().__init__(host, queue_name, exchange_name, FANOUT_EXCHANGE_TYPE)

class DirectExchangeRabbitMQ(MessageMiddlewareExchangeRabbitMQ):
    def __init__(self, host, exchange_name):
        super().__init__(host, exchange_name, DIRECT_EXCHANGE_TYPE)

class FanoutExchangeRabbitMQ(MessageMiddlewareExchangeRabbitMQ):
    def __init__(self, host, exchange_name):
        super().__init__(host, exchange_name, FANOUT_EXCHANGE_TYPE)

    def send(self, message, routing_key=""):
        super().send(message, "")