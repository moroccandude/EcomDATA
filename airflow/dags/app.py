"""
ETL Pipeline DAG for data generation and processing with MinIO storage.
This DAG creates a staging directory, generates sample order and log data, and uploads to MinIO.
"""
import os
import json
import random
import logging
from datetime import datetime
import io
import requests
import pandas as pd
from faker import Faker
from airflow.decorators import dag, task
from airflow.models import Variable
from minio import Minio
from minio.error import S3Error
# Disable SSL warnings for development environment only
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dag(
    dag_id="minio_pipeline_dag",
    schedule_interval="@daily",
    start_date=datetime(2023, 10, 1),
    catchup=False,
    tags=["minio", "nifi", "realtime_processing"],
    default_args={
        "owner": "data_team",
        "retries": 1,
    },
    doc_md=__doc__,
)
def pipeline():
    """Main ETL pipeline for generating sample data and saving to MinIO."""

    @task(task_id="create_dir")
    def create_dir() -> str:
        """Create directory for staging area."""
        logger = logging.getLogger(__name__)
        logger.info("Pipeline DAG started")

        staging_folder = "./data/staging"
        os.makedirs(staging_folder, exist_ok=True)
        Variable.set("folder_path", staging_folder)
        print(f"Working Directory: {os.getcwd()}")
        return staging_folder

    @task(task_id="initialize_minio_connection")
    def initialize_minio_connection():
        """Initialize MinIO connection parameters and create bucket if needed."""
        # MinIO connection parameters - store as variables
        minio_endpoint = "minio:9000"  # Service name in docker-compose
        minio_access_key = "minioadmin"
        minio_secret_key = "minioadmin"
        minio_secure = False  # Set to True if using HTTPS

        # Store connection parameters as variables
        Variable.set("minio_endpoint", minio_endpoint)
        Variable.set("minio_access_key", minio_access_key)
        Variable.set("minio_secret_key", minio_secret_key)
        Variable.set("minio_secure", str(minio_secure))

        # Create a temporary client to check/create bucket
        client = Minio(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )

        # Create buckets if they don't exist
        bucket_name = "data-pipeline"
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created successfully")

        Variable.set("bucket", bucket_name)
        return "MinIO connection initialized"

    def get_minio_client():
        """Helper function to get a MinIO client using stored connection parameters."""
        minio_endpoint = Variable.get("minio_endpoint")
        minio_access_key = Variable.get("minio_access_key")
        minio_secret_key = Variable.get("minio_secret_key")
        minio_secure = Variable.get("minio_secure").lower() == "true"

        return Minio(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )

    @task(task_id="generate_orders")
    def generate_orders(staging_folder: str, num_orders: int = 100) -> dict:
        """Generate sample order data, save to CSV, and upload to MinIO.

        Args:
            staging_folder: Directory path for storing generated data
            num_orders: Number of order records to generate

        Returns:
            Dict with paths to the generated and uploaded files
        """
        fake = Faker()

        orders = [
            {
                "order_id": fake.uuid4(),
                "customer_id": fake.uuid4(),
                "order_date": fake.date_this_year().isoformat(),
                "status": random.choice(["CREATED", "SHIPPED", "DELIVERED", "CANCELLED"]),
                "product_id": fake.uuid4(),
                "quantity": random.randint(1, 5),
                "price": round(random.uniform(10, 500), 2)
            }
            for _ in range(num_orders)
        ]

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        local_filename = f"orders_{timestamp}.csv"
        output_file = os.path.join(staging_folder, local_filename)

        # Save locally
        df = pd.DataFrame(orders)
        df.to_csv(output_file, index=False)

        # Upload to MinIO
        minio_client = get_minio_client()
        bucket_name = Variable.get("bucket")
        minio_path = f"orders/{local_filename}"

        try:
            # Create in-memory buffer for CSV data
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_bytes = csv_buffer.getvalue().encode('utf-8')
            csv_buffer_bytes = io.BytesIO(csv_bytes)

            # Upload to MinIO
            minio_client.put_object(
                bucket_name=bucket_name,
                object_name=minio_path,
                data=csv_buffer_bytes,
                length=len(csv_bytes),
                content_type="text/csv"
            )
            print(f"Successfully uploaded {local_filename} to MinIO bucket {bucket_name}")

        except S3Error as err:
            print(f"Error uploading to MinIO: {err}")

        return {
            "local_path": output_file,
            "minio_path": f"{bucket_name}/{minio_path}"
        }

    @task(task_id="generate_logs")
    def generate_logs(staging_folder: str, num_logs: int = 200) -> dict:
        """Generate sample log data, save to JSON, and upload to MinIO.

        Args:
            staging_folder: Directory path for storing generated data
            num_logs: Number of log records to generate

        Returns:
            Dict with paths to the generated and uploaded files
        """
        fake = Faker()

        logs = [
            {
                "event_id": fake.uuid4(),
                "user_id": fake.uuid4(),
                "event_type": random.choice(["click", "view", "purchase"]),
                "timestamp": datetime.now().isoformat()
            }
            for _ in range(num_logs)
        ]

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        local_filename = f"logs_{timestamp}.json"
        output_file = os.path.join(staging_folder, local_filename)

        # Save locally
        with open(output_file, "w") as f:
            json.dump(logs, f, indent=4)

        # Upload to MinIO
        minio_client = get_minio_client()
        bucket_name = Variable.get("bucket")
        minio_path = f"logs/{local_filename}"

        try:
            # Upload to MinIO
            with open(output_file, 'rb') as file_data:
                file_stat = os.stat(output_file)
                minio_client.put_object(
                    bucket_name=bucket_name,
                    object_name=minio_path,
                    data=file_data,
                    length=file_stat.st_size,
                    content_type="application/json"
                )
            print(f"Successfully uploaded {local_filename} to MinIO bucket {bucket_name}")

        except S3Error as err:
            print(f"Error uploading to MinIO: {err}")

        return {
            "local_path": output_file,
            "minio_path": f"{bucket_name}/{minio_path}"
        }

    @task(task_id="transform_using_nifi", retries=2, retry_delay=30)
    def transform_using_nifi():
        """Trigger NiFi flow for data transformation using REST API with proper SSL handling."""
        try:
            # NiFi connection parameters - updated for HTTPS
            nifi_host = "nifi"  # Service name in docker network
            nifi_port = 8443    # Updated to HTTPS port
            nifi_api_url = f"https://{nifi_host}:{nifi_port}/nifi-api"
            processor_group_id = "21c8e227-0196-1000-55b1-efeba7bbe5dc"  # Your processor group ID

            # Endpoint for starting a process group
            endpoint = f"{nifi_api_url}/flow/process-groups/{processor_group_id}/run-status"

            # Payload for starting the process group
            payload = {"state": "RUNNING"}

            print(f"Connecting to NiFi at: {endpoint}")

            # Making the API request with SSL verification disabled
            # Note: In production, use proper certificates instead of verify=False
            response = requests.put(
                endpoint,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                verify=False,  # Disable SSL verification - only for testing!
                # auth=('nifi_username', 'nifi_password')  # Uncomment if authentication is needed
            )

            if response.status_code == 200:
                print(f"Successfully started NiFi processor group {processor_group_id}")
                return True
            else:
                print(f"Failed to start NiFi processor group. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False

        except requests.exceptions.SSLError as ssl_err:
            print(f"SSL Error connecting to NiFi: {str(ssl_err)}")
            print("Check if your NiFi instance is using HTTPS and if certificates are set up correctly.")
            raise
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection Error: {str(conn_err)}")
            print("This might indicate that NiFi is not running or not accessible at the specified host/port.")
            print("Check if NiFi is running and network connectivity between Airflow and NiFi.")
            raise
        except Exception as e:
            print(f"Error triggering NiFi processor group: {str(e)}")
            raise

    @task(task_id="check_nifi_completion", trigger_rule="all_done", retries=3, retry_delay=60)
    def check_nifi_completion():
        """Check if the NiFi process group has completed processing."""
        try:
            # NiFi connection parameters
            nifi_host = "nifi"
            nifi_port = 8443  # Updated to HTTPS port
            nifi_api_url = f"https://{nifi_host}:{nifi_port}/nifi-api"
            processor_group_id = "21c8e227-0196-1000-55b1-efeba7bbe5dc"

            # Endpoint for checking process group status
            endpoint = f"{nifi_api_url}/flow/process-groups/{processor_group_id}/status"

            print(f"Checking NiFi status at: {endpoint}")

            # Making the API request with SSL verification disabled
            response = requests.get(
                endpoint,
                verify=False,  # Disable SSL verification - only for testing!
                # auth=('nifi_username', 'nifi_password')  # Uncomment if authentication is needed
            )

            if response.status_code == 200:
                status_data = response.json()
                process_group_status = status_data.get('processGroupStatus', {})
                active_threads = process_group_status.get('aggregateSnapshot', {}).get('activeThreadCount', 0)

                if active_threads == 0:
                    print(f"NiFi process group {processor_group_id} has completed processing")
                    return True
                else:
                    print(f"NiFi process group {processor_group_id} still has {active_threads} active threads")
                    return False
            else:
                print(f"Failed to check NiFi processor group status. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False

        except requests.exceptions.SSLError as ssl_err:
            print(f"SSL Error checking NiFi status: {str(ssl_err)}")
            raise
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection Error checking NiFi status: {str(conn_err)}")
            raise
        except Exception as e:
            print(f"Error checking NiFi processor group status: {str(e)}")
            raise

    @task(task_id="summarize_results")
    def summarize_results(orders_info: dict, logs_info: dict, nifi_completion=None):
        """Log summary of the data generation and upload process."""
        print("=" * 50)
        print("ETL Pipeline Execution Summary")
        print("=" * 50)
        print(f"Orders data:")
        print(f"  - Local path: {orders_info['local_path']}")
        print(f"  - MinIO path: {orders_info['minio_path']}")
        print(f"Logs data:")
        print(f"  - Local path: {logs_info['local_path']}")
        print(f"  - MinIO path: {logs_info['minio_path']}")
        if nifi_completion is not None:
            print(f"NiFi processing: {'Completed' if nifi_completion else 'Failed or Incomplete'}")
        print("=" * 50)
        return "Pipeline execution completed"

    # Define the task dependencies
    staging_folder = create_dir()
    minio_init = initialize_minio_connection()
    orders_info = generate_orders(staging_folder)
    logs_info = generate_logs(staging_folder)
    nifi_transform = transform_using_nifi()
    nifi_completion = check_nifi_completion()
    summary = summarize_results(orders_info, logs_info, nifi_completion)

    # Set dependencies
    staging_folder >> minio_init >> [orders_info, logs_info] >> nifi_transform >> nifi_completion >> summary


# Instantiate the DAG
minio_pipeline_dag = pipeline()