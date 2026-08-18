package tests

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"slices"
	"strconv"
	"time"

	m "github.com/7574-sistemas-distribuidos/tp-mom/golang/internal/middleware"
)

// -----------------------------------------------------------------------------
// HELP FUNCTIONS
// -----------------------------------------------------------------------------

func GetConnectionDetails() m.ConnSettings {
	port, err := strconv.ParseInt(os.Getenv("RABBITMQ_PORT"), 10, 64)
	if err != nil {
		panic("Invalid Broker port number")
	}
	return m.ConnSettings{Hostname: os.Getenv("RABBITMQ_HOST"), Port: int(port)}
}

func GetWaitOptions() WaitOptions {
	port, err := strconv.ParseInt(os.Getenv("API_PORT"), 10, 64)
	if err != nil {
		panic("Invalid Queue port number")
	}
	return WaitOptions{
		Host:         os.Getenv("RABBITMQ_HOST"),
		Port:         int(port),
		User:         "guest",
		Pass:         "guest",
		Vhost:        "%2F",
		Timeout:      10 * time.Second,
		PollInterval: 100 * time.Millisecond,
	}
}

// Remove removes the first occurrence of an element from a slice
func Remove[T comparable](slice []T, element T) []T {
	for i, value := range slice {
		if value == element {
			return slices.Delete(slice, i, i+1)
		}
	}
	return slice
}

type WaitOptions struct {
	Host         string
	Port         int
	User         string
	Pass         string
	Vhost        string
	Timeout      time.Duration
	PollInterval time.Duration
}

type binding struct {
	Source          string `json:"source"`
	Destination     string `json:"destination"`
	DestinationType string `json:"destination_type"`
	RoutingKey      string `json:"routing_key"`
}

func WaitForExchangeBindings(
	exchangeName string,
	key string,
	expectedQueues int,
	opts WaitOptions,
) error {
	/*
	   Esperar a que todos los "bindings" esperados de las colas al exchange de prueba existan.

	   ACLARACIÓN: Esta función sincroniza los "bindings" en un contexto en donde:
	   - No podemos extender el middleware ni agregarle lógica
	   - No podemos asumir la existencia de mecanismos de sincronización en el middleware
	   - Agregar lógica adicional de comunicación entre componentes complejizaría los casos de prueba

	   Si se te presenta un caso que pensás que amerita una solución similar; evalua exhaustivamente que no haya mejores opciones;
	   y recordá, este tipo de lógica debería estar en el middleware, que es el componente que abstrae la lógica de comunicación.
	*/
	deadline := time.Now().Add(opts.Timeout)
	for time.Now().Before(deadline) {
		bindings, err := getExchangeBindings(exchangeName, opts)
		if err != nil {
			return fmt.Errorf("failed to get bindings: %w", err)
		}

		uniqueQueues := uniqueDestinations(bindings, key)
		if len(uniqueQueues) >= expectedQueues {
			return nil
		}

		time.Sleep(opts.PollInterval)
	}
	return fmt.Errorf("timed out waiting for %d queues on exchange %q", expectedQueues, exchangeName)
}

func getExchangeBindings(exchangeName string, opts WaitOptions) ([]binding, error) {
	url := fmt.Sprintf("http://%s:%d/api/exchanges/%s/%s/bindings/source",
		opts.Host, opts.Port, opts.Vhost, exchangeName)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.SetBasicAuth(opts.User, opts.Pass)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("management API returned status %d", resp.StatusCode)
	}

	var bindings []binding
	if err := json.NewDecoder(resp.Body).Decode(&bindings); err != nil {
		return nil, err
	}
	return bindings, nil
}

func uniqueDestinations(bindings []binding, key string) []string {
	seen := make(map[string]struct{})
	for _, b := range bindings {
		if b.DestinationType == "queue" && b.RoutingKey == key {
			seen[b.Destination] = struct{}{}
		}
	}
	result := make([]string, 0, len(seen))
	for name := range seen {
		result = append(result, name)
	}
	return result
}
