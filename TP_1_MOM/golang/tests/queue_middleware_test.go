package tests

import (
	"testing"

	f "github.com/7574-sistemas-distribuidos/tp-mom/golang/internal/factory"
	m "github.com/7574-sistemas-distribuidos/tp-mom/golang/internal/middleware"
	"github.com/stretchr/testify/assert"
)

func GetQueueMiddleware(queueName string) (m.Middleware, error) {
	return f.CreateQueueMiddleware(queueName, GetConnectionDetails())
}

type QueueProdSettings struct {
	MessagesByQueue map[string][]string
}

type QueueConsSettings struct {
	QueueName string
}

// ----------------------------------------------------------------------------
// GENERAL TESTS
// ----------------------------------------------------------------------------
func TestCanConnect(t *testing.T) {
	producerMiddleware, initErr := GetQueueMiddleware("TestCanConnect")
	assert.NoError(t, initErr)

	closeErr := producerMiddleware.Close()
	assert.NoError(t, closeErr)
}

// ----------------------------------------------------------------------------
// PRODUCER CONSUMER TESTS
// ----------------------------------------------------------------------------
func TestOneToOne(t *testing.T) {

	// Arrange
	producersDeclaration := []QueueProdSettings{
		{MessagesByQueue: map[string][]string{
			"TestOneToOne": {
				"JavaScript",
				"Python",
				"Java",
				"C",
				"C++",
				"C#",
				"TypeScript",
				"Ruby",
				"Go",
				"Rust",
				"Swift",
				"Kotlin",
				"PHP",
				"SQL",
				"Assembly",
			},
		}},
	}

	consumersDeclaration := []QueueConsSettings{
		{QueueName: "TestOneToOne"},
	}

	DoTestQueue(t, producersDeclaration, consumersDeclaration)
}

func TestOneToMany(t *testing.T) {

	// Arrange
	producersDeclaration := []QueueProdSettings{
		{MessagesByQueue: map[string][]string{
			"TestOneToMany": {
				"Buenos Aires",
				"Córdoba",
				"Rosario",
				"Mendoza",
				"San Miguel de Tucumán",
				"La Plata",
				"Mar del Plata",
				"Salta",
				"Santa Fe",
				"San Juan",
				"Resistencia",
				"Neuquén",
				"San Salvador de Jujuy",
				"Posadas",
				"Corrientes",
				"Bahía Blanca",
				"San Luis",
				"Bariloche",
				"Ushuaia",
				"Río Gallegos",
			},
		}},
	}

	consumersDeclaration := []QueueConsSettings{
		{QueueName: "TestOneToMany"},
		{QueueName: "TestOneToMany"},
		{QueueName: "TestOneToMany"},
		{QueueName: "TestOneToMany"},
		{QueueName: "TestOneToMany"},
	}

	DoTestQueue(t, producersDeclaration, consumersDeclaration)
}

func TestManyToOne(t *testing.T) {

	// Arrange
	producersDeclaration := []QueueProdSettings{
		{MessagesByQueue: map[string][]string{
			"TestManyToOne": {"Buenos Aires", "Córdoba", "Rosario", "Mendoza", "San Miguel de Tucumán"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToOne": {"La Plata", "Mar del Plata", "Salta", "Santa Fe", "San Juan"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToOne": {"Resistencia", "Neuquén", "San Salvador de Jujuy", "Posadas", "Corrientes"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToOne": {"Bahía Blanca", "San Luis", "Bariloche", "Ushuaia", "Río Gallegos"},
		}},
	}

	consumersDeclaration := []QueueConsSettings{
		{QueueName: "TestManyToOne"},
	}

	DoTestQueue(t, producersDeclaration, consumersDeclaration)
}

func TestManyToMany(t *testing.T) {

	// Arrange
	producersDeclaration := []QueueProdSettings{
		{MessagesByQueue: map[string][]string{
			"TestManyToMany": {"Buenos Aires", "Córdoba", "Rosario", "Mendoza", "San Miguel de Tucumán"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToMany": {"La Plata", "Mar del Plata", "Salta", "Santa Fe", "San Juan"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToMany": {"Resistencia", "Neuquén", "San Salvador de Jujuy", "Posadas", "Corrientes"},
		}},
		{MessagesByQueue: map[string][]string{
			"TestManyToMany": {"Bahía Blanca", "San Luis", "Bariloche", "Ushuaia", "Río Gallegos"},
		}},
	}

	consumersDeclaration := []QueueConsSettings{
		{QueueName: "TestManyToMany"},
		{QueueName: "TestManyToMany"},
		{QueueName: "TestManyToMany"},
		{QueueName: "TestManyToMany"},
	}

	DoTestQueue(t, producersDeclaration, consumersDeclaration)
}

// ----------------------------------------------------------------------------
// HELP FUNCTIONS
// ----------------------------------------------------------------------------
func DoTestQueue(
	t *testing.T,
	producersDeclaration []QueueProdSettings,
	consumersDeclaration []QueueConsSettings,
) {
	/*
	   El primer argumento de esta función es un arreglo de configuraciones para los productores,
	   donde se declaran los mensajes que cada uno mandará a cada cola.
	   El segundo es la declaración de los consumidores y de qué cola estarán consumiendo mensajes.
	   En base a estos parámetros se configura la topología y se determina si la ejecución fue exitosa o no
	   dependiendo de si todos los mensajes enviados fueron recibidos y procesados por los consumidores exactamente una vez.
	*/

	// Arrange
	msgsFanIn := make(chan string)
	producersByQueue := make(map[string]m.Middleware)
	numConsumersByQueue := make(map[string]int)
	for _, producerOpts := range producersDeclaration {
		for queueName := range producerOpts.MessagesByQueue {
			middleware, err := GetQueueMiddleware(queueName)
			assert.NoError(t, err)
			producersByQueue[queueName] = middleware

			numConsumersByQueue[queueName] = 0
		}
	}

	consumers := make([]m.Middleware, 0)
	for _, consumerOpts := range consumersDeclaration {
		middleware, err := GetQueueMiddleware(consumerOpts.QueueName)
		assert.NoError(t, err)
		consumers = append(consumers, middleware)
		numConsumersByQueue[consumerOpts.QueueName] += 1

		forwardToChannel := func(msg m.Message, ack func(), nack func()) {
			msgsFanIn <- msg.Body
			ack()
		}

		go middleware.StartConsuming(forwardToChannel)
	}

	// Act
	for _, producerOpts := range producersDeclaration {
		for queueName, messages := range producerOpts.MessagesByQueue {
			for _, msg := range messages {
				producersByQueue[queueName].Send(m.Message{Body: msg})
			}
		}
	}

	expectedDeliveries := make([]string, 0)
	for _, producerOpts := range producersDeclaration {
		for _, messages := range producerOpts.MessagesByQueue {
			expectedDeliveries = append(expectedDeliveries, messages...)
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

	for _, producerMiddleware := range producersByQueue {
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
