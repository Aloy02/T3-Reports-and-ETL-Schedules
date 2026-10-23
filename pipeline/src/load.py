"""Module for loading CSV data into S3 as Parquet files."""

from pathlib import Path
import io
import boto3
from botocore.exceptions import ClientError
import awswrangler as wr
import pandas as pd
from logger import setup_logger

logger = setup_logger()

# S3 Configuration
INPUT_BUCKET_NAME = "c26-aloysius-t3-s3"
PREFIX = "t3-input"
RAW_DATA_PREFIX = "raw-data"
MASTER_DATA_PREFIX = "master-data"

s3_client = boto3.client("s3")

CLEAN_DATA_DIR = Path("../priv_clean_data")

S3_TRANSACTION_PATH = f"s3://{INPUT_BUCKET_NAME}/{PREFIX}/transactions/"
S3_PAYMENT_PATH = f"s3://{INPUT_BUCKET_NAME}/{PREFIX}/payment_methods/"
S3_TRUCK_PATH = f"s3://{INPUT_BUCKET_NAME}/{PREFIX}/trucks/"


def load_transactions():
    """Finds all CSV files in the clean data directory and appends them to S3 in Parquet format."""

    # Locate all CSV batch files recursively in clean data path
    csv_files = list(CLEAN_DATA_DIR.rglob("*.csv"))

    if not csv_files:
        logger.warning(
            "No transaction CSV files found in %s to load.", CLEAN_DATA_DIR)
        return

    logger.info("Found %d CSV file(s) to process.", len(csv_files))

    # Read and concatenate all new batch files
    df_list = [pd.read_csv(f) for f in csv_files]
    df = pd.concat(df_list, ignore_index=True)

    if df.empty:
        logger.warning(
            "Combined transaction dataset is empty. Skipping upload.")
        return

    # 1. Drop rows where 'at' couldn't be parsed (prevents __HIVE_DEFAULT_PARTITION__ files)
    df = df.dropna(subset=["at"])

    # 2. Convert 'at' to datetime and cast 'date_partition' explicitly to string (NOT category)
    df["at"] = pd.to_datetime(df["at"])
    df["date_partition"] = df["at"].dt.strftime("%Y_%m_%d").astype(str)

    # 3. Filter out any leftover empty groups or blank partition values
    df = df[df["date_partition"].str.strip() != ""]

    # 4. Write to S3
    res = wr.s3.to_parquet(
        df=df,
        path=S3_TRANSACTION_PATH,
        dataset=True,
        mode="append",
        partition_cols=["date_partition"]
    )

    logger.info(
        "Successfully loaded %d transaction rows to S3. Written files:", len(df))
    for path in res["paths"]:
        logger.info(" - %s", path)


def load_payment_methods():
    """Loads payment methods dimension table to S3 (Full snapshot overwrite)."""
    payment_s3_key = f"{MASTER_DATA_PREFIX}/DIM_Payment_Method.csv"
    try:
        response = s3_client.get_object(Bucket=INPUT_BUCKET_NAME, Key=payment_s3_key)
        df = pd.read_csv(io.BytesIO(response['Body'].read()))
    except ClientError as e:
        logger.warning("Payment CSV missing in S3 at %s. Skipping. Error: %s",
                       payment_s3_key, e)
        return

    res = wr.s3.to_parquet(
        df=df,
        path=S3_PAYMENT_PATH,
        dataset=True,
        mode="overwrite"
    )

    logger.info("Payment methods snapshot complete (%d rows):", len(df))
    for path in res["paths"]:
        logger.info(" - %s", path)


def load_trucks():
    """Loads truck dimension table to S3 (Full snapshot overwrite)."""
    truck_s3_key = f"{MASTER_DATA_PREFIX}/DIM_Truck.csv"
    try:
        response = s3_client.get_object(Bucket=INPUT_BUCKET_NAME, Key=truck_s3_key)
        df = pd.read_csv(io.BytesIO(response['Body'].read()))
    except ClientError as e:
        logger.warning("Truck CSV missing in S3 at %s. Skipping. Error: %s",
                       truck_s3_key, e)
        return

    res = wr.s3.to_parquet(
        df=df,
        path=S3_TRUCK_PATH,
        dataset=True,
        mode="overwrite"
    )

    logger.info("Trucks dimension snapshot complete (%d rows):", len(df))
    for path in res["paths"]:
        logger.info(" - %s", path)


def load():
    """Load all processed CSV data into S3 as Parquet files."""
    logger.info("Starting S3 Parquet Load Pipeline...")

    logger.info("Loading transaction batches to S3...")
    load_transactions()

    logger.info("Loading payment methods to S3...")
    load_payment_methods()

    logger.info("Loading truck data to S3...")
    load_trucks()

    logger.info("S3 Parquet Load Pipeline finished successfully.")


if __name__ == "__main__":
    load()
