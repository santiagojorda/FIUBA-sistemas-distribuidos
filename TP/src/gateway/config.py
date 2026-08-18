import os
import json

class GatewayConfig:
    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 12345
    DEFAULT_MOM_HOST = "localhost"
    DEFAULT_WORKERS = 1
    
    HEADER_TIMESTAMP = "Timestamp"
    HEADER_BANK_NAME = "Bank Name"
    DEFAULT_HASH_FIELD = "Bank ID"

    def __init__(self):
        self.server_host = os.environ.get("SERVER_HOST", self.DEFAULT_HOST)
        self.server_port = int(os.environ.get("SERVER_PORT", self.DEFAULT_PORT))
        self.mom_host = os.getenv("MOM_HOST", self.DEFAULT_MOM_HOST)
        
        output_str = os.getenv("OUTPUTS_QUEUE", os.getenv("OUTPUT_QUEUE", ""))
        self.output_queues = [q.strip() for q in output_str.split(",") if q.strip()]
        
        input_str = os.getenv("INPUTS_QUEUE", os.getenv("INPUT_QUEUE", ""))
        self.input_queues = [q.strip() for q in input_str.split(",") if q.strip()]
        
        bank_env = os.getenv("BANK_QUEUE", "{}")
        self.bank_queue_config = json.loads(bank_env)
        
        self.num_queries = len(self.input_queues)
        self.heartbeat_interval_seconds = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5"))
        eofs_str = os.getenv("EOF_COUNTS_PER_QUEUE", "{}")
        self.eofs_esperados = json.loads(eofs_str)  # {"q2_results": 6, ...}; default 1 si no figura