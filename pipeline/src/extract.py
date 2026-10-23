"""Data extraction utility for the Food Truck Analytics pipeline."""

import json
import sys
from contextlib import contextmanager
from io import StringIO
from typing import Any, Generator

import boto3
from botocore.exceptions import ClientError
import pandas as pd
from connect import check_connection, get_connection
from logger import setup_logger

S3_BUCKET_NAME = "c26-aloysius-t3-s3"
STATE_FILE_KEY = "state.json"
S3_RAW_DATA_PREFIX = "raw-data"
S3_MASTER_DATA_PREFIX = "master-data"

logger = setup_logger()
s3_client = boto3.client("s3")


# --- State Management (S3) ---

def get_last_processed_id() -> int:
    """Retrieve the last processed transaction ID from S3."""
    try:
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME, Key=STATE_FILE_KEY)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data.get("last_processed_id", 0)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            logger.warning(
                "S3 state file missing in bucket %s. Starting from ID 0.", S3_BUCKET_NAME)
            save_last_processed_id(0)
            return 0
        logger.error(
            "Failed to read state file from S3: %s. Defaulting to 0.", e)
        return 0
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            "Failed to parse state file from S3: %s. Defaulting to 0.", e)
        return 0


def save_last_processed_id(last_id: int) -> None:
    """Persist the highest processed transaction ID to S3."""
    try:
        json_data = json.dumps({"last_processed_id": last_id}, indent=2)
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=STATE_FILE_KEY,
            Body=json_data,
            ContentType="application/json",
        )
        logger.info("Updated S3 watermark ID to %d in bucket %s.",
                    last_id, S3_BUCKET_NAME)
    except ClientError as e:
        logger.error("Failed to save state file to S3: %s", e)


def save_dataframe_to_s3(df: pd.DataFrame, s3_key: str) -> None:
    """Save a DataFrame to S3 as CSV."""
    try:
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=csv_buffer.getvalue().encode("utf-8"),
            ContentType="text/csv",
        )
        logger.info("Saved data to S3: s3://%s/%s (%d rows)",
                    S3_BUCKET_NAME, s3_key, len(df))
    except ClientError as e:
        logger.error("Failed to save data to S3: %s", e)


# --- Database Helpers ---

@contextmanager
def get_db_cursor() -> Generator[Any, None, None]:
    """Context manager to ensure database connection and cursor cleanup."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.close()


# --- Extraction Logic ---

def extract_fact_transaction_3hr_batch() -> bool:
    """Extract only unprocessed records and save them to S3."""
    last_id = get_last_processed_id()
    logger.info("Extracting transactions strictly greater than ID: %d", last_id)

    query = """
        SELECT *
        FROM FACT_Transaction
        WHERE transaction_id > %s
        ORDER BY transaction_id ASC;
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, (last_id,))
        rows = cursor.fetchall()

    if not rows:
        logger.info(
            "No new transactions found since ID %d. Skipping output.", last_id)
        return False

    df = pd.DataFrame(rows)

    max_id = int(df["transaction_id"].max())
    s3_key = f"{S3_RAW_DATA_PREFIX}/FACT_Transaction.csv"
    save_dataframe_to_s3(df, s3_key)

    save_last_processed_id(max_id)

    logger.info("Saved %d new records to S3. New watermark ID: %d",
                len(df), max_id)
    return True


def extract_dim_payment_method() -> None:
    """Dimension tables are full snapshots (overwritten daily or per run)."""
    query = "SELECT * FROM DIM_Payment_Method;"

    with get_db_cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    if rows:
        df = pd.DataFrame(rows)
        s3_key = f"{S3_MASTER_DATA_PREFIX}/DIM_Payment_Method.csv"
        save_dataframe_to_s3(df, s3_key)
        logger.info(
            "Dimension table DIM_Payment_Method updated (%d rows).", len(rows))


def extract_dim_truck() -> None:
    """Dimension tables are full snapshots (overwritten daily or per run)."""
    query = "SELECT * FROM DIM_Truck;"

    with get_db_cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    if rows:
        df = pd.DataFrame(rows)
        s3_key = f"{S3_MASTER_DATA_PREFIX}/DIM_Truck.csv"
        save_dataframe_to_s3(df, s3_key)
        logger.info("Dimension table DIM_Truck updated (%d rows).", len(rows))


def extract() -> bool:
    """Extract both dimension and fact tables."""
    extract_dim_payment_method()
    extract_dim_truck()
    return extract_fact_transaction_3hr_batch()


if __name__ == "__main__":
    try:
        check_connection()
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        sys.exit(1)

    extract_dim_payment_method()
    extract_dim_truck()
    extract_fact_transaction_3hr_batch()
