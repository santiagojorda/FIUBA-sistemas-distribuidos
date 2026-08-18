package tests

import (
	"slices"
	"testing"

	f "github.com/7574-sistemas-distribuidos/tp-mom/golang/internal/factory"
	m "github.com/7574-sistemas-distribuidos/tp-mom/golang/internal/middleware"
	"github.com/stretchr/testify/assert"
)

func GetExchangeMiddleware(exchange string, keys []string) (m.Middleware, error) {
	return f.CreateExchangeMiddleware(exchange, keys, GetConnectionDetails())
}

var waitOpts = GetWaitOptions()

type ExchangeProducerOpts struct {
	MessagesByRoutingKey map[string][]string
}

type ExchangeConsumerOpts struct {
	RoutingKeys []string
}

const EXCHANGE_NAME = "test_exchange"

// ----------------------------------------------------------------------------
// GENERAL TESTS
// ----------------------------------------------------------------------------
func TestCanConnectExchange(t *testing.T) {
	producerMiddleware, initErr := GetExchangeMiddleware("test_exchange", []string{"TestCanConnect"})
	assert.NoError(t, initErr)

	closeErr := producerMiddleware.Close()
	assert.NoError(t, closeErr)
}

// ----------------------------------------------------------------------------
// DIRECT MESSAGING TESTS
// ----------------------------------------------------------------------------
func TestOneToOneExchange(t *testing.T) {
	// Arrange
	const routeKey = "TestOneToOne"
	producersDeclaration := []ExchangeProducerOpts{
		{MessagesByRoutingKey: map[string][]string{
			routeKey: {
				"Lionel Messi",
				"Diego Maradona",
				"Ángel Di María",
				"Julián Álvarez",
				"Enzo Fernández",
				"Alexis Mac Allister",
				"Emiliano Martínez",
				"Lautaro Martínez",
				"Rodrigo De Paul",
				"Cuti Romero",
			},
		}},
	}

	consumersDeclaration := []ExchangeConsumerOpts{
		{RoutingKeys: []string{routeKey}},
	}

	DoTestExchange(t, producersDeclaration, consumersDeclaration)
}

func TestManyToOneExchange(t *testing.T) {
	// Arrange
	const routeKey = "TestManyToOne_A"
	producersDeclaration := []ExchangeProducerOpts{
		{MessagesByRoutingKey: map[string][]string{
			routeKey: {
				"Buenos Aires",
				"Córdoba",
				"Santa Fe",
				"Mendoza",
				"Tucumán",
				"Entre Ríos",
				"Salta",
				"Misiones",
			},
		}},
		{MessagesByRoutingKey: map[string][]string{
			routeKey: {
				"Chaco",
				"Corrientes",
				"Santiago del Estero",
				"San Juan",
				"Jujuy",
				"Río Negro",
				"Neuquén",
				"Formosa",
			},
		}},
		{MessagesByRoutingKey: map[string][]string{
			routeKey: {
				"Chubut",
				"San Luis",
				"Catamarca",
				"La Rioja",
				"La Pampa",
				"Santa Cruz",
				"Tierra del Fuego",
			},
		}},
	}

	consumersDeclaration := []ExchangeConsumerOpts{
		{RoutingKeys: []string{routeKey}},
	}

	DoTestExchange(t, producersDeclaration, consumersDeclaration)
}

// ----------------------------------------------------------------------------
// BROADCAST MESSAGING TESTS
// ----------------------------------------------------------------------------
func TestOneToManyExchange(t *testing.T) {
	// Arrange
	const routeKey = "TestOneToMany"
	producersDeclaration := []ExchangeProducerOpts{
		{MessagesByRoutingKey: map[string][]string{
			routeKey: {
				"Ferrari",
				"Porsche",
				"Lamborghini",
				"Mercedes-Benz",
				"BMW",
				"Audi",
				"Tesla",
				"Toyota",
				"Ford",
				"Chevrolet",
				"Aston Martin",
				"Mclaren",
			},
		}},
	}

	consumersDeclaration := []ExchangeConsumerOpts{
		{RoutingKeys: []string{routeKey}},
		{RoutingKeys: []string{routeKey}},
		{RoutingKeys: []string{routeKey}},
	}

	DoTestExchange(t, producersDeclaration, consumersDeclaration)
}

func TestManyToManyExchange(t *testing.T) {
	// Arrange
	const routeKeyA = "TestManyToMany_A"
	const routeKeyB = "TestManyToMany_B"
	producersDeclaration := []ExchangeProducerOpts{
		{MessagesByRoutingKey: map[string][]string{
			routeKeyA: {"Audi", "Ferrari", "Mclaren"},
			routeKeyB: {"Boeing", "Cesna", "Embraer", "Airbus", "Piper"},
		}},
	}

	consumersDeclaration := []ExchangeConsumerOpts{
		{RoutingKeys: []string{routeKeyA}},
		{RoutingKeys: []string{routeKeyA, routeKeyB}},
		{RoutingKeys: []string{routeKeyB}},
	}

	DoTestExchange(t, producersDeclaration, consumersDeclaration)
}

// ----------------------------------------------------------------------------
// HELP FUNCTIONS
// ----------------------------------------------------------------------------
func DoTestExchange(
	t *testing.T,
	producersDeclaration []ExchangeProducerOpts,
	consumersDeclaration []ExchangeConsumerOpts,
) {
	/*
	   El primer argumento de esta función es un arreglo de configuraciones para los productores,
	   donde se declaran los mensajes que cada uno mandará al exchange usando cada routing key.
	   El segundo es la declaración de los consumidores y con qué topics se conectará al exchange.
	   En base a estos parámetros se configura la topología y se determina si la ejecución fue exitosa o no
	   dependiendo de si todos los mensajes enviados fueron recibidos y procesados por los consumidores.
	   Se contempla también que los mensajes se duplicarán en los casos donde hay más de un consumidor por routing key
	   esperando que la cantidad de veces que se procesa el mensaje sea igual a la cantidad de consumidores asociados a dicha key.
	*/

	// Arrange
	msgsFanIn := make(chan string)
	producerByKey := make(map[string]m.Middleware)
	numConsumersByKey := make(map[string]int)
	for _, producerOpts := range producersDeclaration {
		for routingKey := range producerOpts.MessagesByRoutingKey {
			middleware, err := GetExchangeMiddleware(EXCHANGE_NAME, []string{routingKey})
			assert.NoError(t, err)
			producerByKey[routingKey] = middleware
			numConsumersByKey[routingKey] = 0
		}
	}

	consumers := make([]m.Middleware, 0)
	for _, consumerOpts := range consumersDeclaration {
		middleware, err := GetExchangeMiddleware(EXCHANGE_NAME, consumerOpts.RoutingKeys)
		assert.NoError(t, err)
		consumers = append(consumers, middleware)
		for _, routingKey := range consumerOpts.RoutingKeys {
			numConsumersByKey[routingKey] += 1
		}

		forwardToChannel := func(msg m.Message, ack func(), nack func()) {
			msgsFanIn <- msg.Body
			ack()
		}

		go middleware.StartConsuming(forwardToChannel)
	}

	// Act
	for _, producerOpts := range producersDeclaration {
		for routingKey, messages := range producerOpts.MessagesByRoutingKey {
			WaitForExchangeBindings(EXCHANGE_NAME, routingKey, numConsumersByKey[routingKey], waitOpts)
			for _, msg := range messages {
				producerByKey[routingKey].Send(m.Message{Body: msg})
			}
		}
	}

	expectedDeliveries := make([]string, 0)
	for _, producerOpts := range producersDeclaration {
		for routingKey, msgs := range producerOpts.MessagesByRoutingKey {
			numConsumersForKey := 0
			for _, consumerOpts := range consumersDeclaration {
				if slices.Contains(consumerOpts.RoutingKeys, routingKey) {
					numConsumersForKey += 1
				}
			}
			for range numConsumersForKey {
				expectedDeliveries = append(expectedDeliveries, msgs...)
			}
		}
	}

	comparisonResults := make([]bool, 0)

	deliveries := len(expectedDeliveries)
	for range deliveries {
		Remove(expectedDeliveries, <-msgsFanIn) // Does nothing if not present
	}
	close(msgsFanIn)

	// Assert
	assert.Empty(t, comparisonResults)

	for _, producerMiddleware := range producerByKey {
		closeErr := producerMiddleware.Close()
		assert.NoError(t, closeErr)
	}

	for _, consumerMiddleware := range consumers {
		stopErr := consumerMiddleware.StopConsuming()
		closeErr := consumerMiddleware.Close()
		assert.NoError(t, stopErr)
		assert.NoError(t, closeErr)
	}
}
