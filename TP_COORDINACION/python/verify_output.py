import csv
import yaml
import logging
import subprocess

from fruit_item import FruitItem

DOCKER_FILE_PATH = "./docker-compose.yaml"


class ClientValidationError(Exception):

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def await_client_containers(client_services_name):
    result = subprocess.run(
        ["docker", "container", "wait"] + client_services_name, capture_output=True
    )

    zero_exit_code_count = 0
    for char in result.stdout.decode("utf-8"):
        if char == "0":
            zero_exit_code_count += 1

    if zero_exit_code_count != len(client_services_name):
        raise ClientValidationError("One or more clients exited with an error code")


def find_environment_variable(environment_variables, target_environment_variable):
    for environment_variable in environment_variables:
        [name, value] = environment_variable.split("=")
        if name == target_environment_variable:
            return value
    return None


def build_input_fruit_top(input_file):
    try:
        amount_by_fruit = {}
        with open(input_file, newline="\n") as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=",", quotechar='"')
            for row in csv_reader:
                [fruit, amount] = row
                new_fruit_item = FruitItem(fruit, int(amount))
                current_fruit_item = amount_by_fruit.get(fruit, FruitItem(fruit, 0))
                amount_by_fruit[fruit] = current_fruit_item + new_fruit_item

        fruit_top = sorted(amount_by_fruit.values())
        fruit_top.reverse()
        return fruit_top
    except Exception as e:
        logging.error(e)
        raise ClientValidationError("Couldn't build input file fruit top")


def read_output_fruit_top(output_file):
    try:
        fruit_top = []
        with open(output_file, newline="\n") as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=",", quotechar='"')
            for row in csv_reader:
                [fruit, amount] = row
                fruit_top.append(FruitItem(fruit, int(amount)))
        return fruit_top
    except Exception as e:
        logging.error(e)
        raise ClientValidationError("Couldn't read output file fruit top")


def verify_client_output(top_size, client_service):
    client_name = client_service["container_name"]
    logging.info(client_name)
    environment = client_service["environment"]
    input_file = "." + find_environment_variable(environment, "INPUT_FILE")
    output_file = "." + find_environment_variable(environment, "OUTPUT_FILE")
    environment = client_service["environment"]

    if not input_file or not output_file:
        raise ClientValidationError("Bad file environment variable config")

    expected_fruit_top = build_input_fruit_top(input_file)
    received_fruit_top = read_output_fruit_top(output_file)

    i = 0
    mismtach_found = False
    while i < top_size:
        expected_fruit_item = expected_fruit_top[i]
        received_fruit_item = received_fruit_top[i] or FruitItem("-", -1)

        if expected_fruit_item == received_fruit_item:
            logging.info(f"{received_fruit_item}")
        else:
            logging.info(f"{received_fruit_item} - Expected: {expected_fruit_item}")
            mismtach_found = True

        i += 1
    if mismtach_found:
        raise ClientValidationError("Mistmatch in expected and received fruit tops")

    if top_size != len(received_fruit_top):
        raise ClientValidationError(
            f"Mistmatch in expected and received fruit tops length {len(received_fruit_top)}/{top_size}"
        )

    logging.info("OK")


def find_top_size(services):
    for service in services.values():
        top_size = find_environment_variable(service["environment"], "TOP_SIZE")
        if top_size:
            return int(top_size)


def main():
    logging.basicConfig(level=logging.INFO)

    try:
        with open(DOCKER_FILE_PATH, "r") as docker_compose_file:
            parsed_docker_compose_file = yaml.safe_load(docker_compose_file)
            services = parsed_docker_compose_file["services"]
            client_services_name = list(
                filter(
                    lambda service_key: "client"
                    in services[service_key]["build"]["dockerfile"],
                    services.keys(),
                )
            )
            top_size = find_top_size(services)
            logging.info("Awaiting client containers to exit...")
            await_client_containers(client_services_name)
            logging.info("Validating clients...")
            for client_service_name in client_services_name:
                client_service = services[client_service_name]
                verify_client_output(top_size, client_service)
            logging.info("All fruit tops match the expected results")
    except ClientValidationError as e:
        logging.error(e.message)
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    main()
