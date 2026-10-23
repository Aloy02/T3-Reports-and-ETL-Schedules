import io
import boto3
from botocore.exceptions import ClientError
import pandas as pd
from logger import setup_logger
from pathlib import Path

logger = setup_logger()

S3_BUCKET_NAME = "c26-aloysius-t3-s3"
S3_RAW_DATA_PREFIX = "raw-data"
S3_MASTER_DATA_PREFIX = "master-data"

s3_client = boto3.client("s3")

transactions_fact_s3_key = f"{S3_RAW_DATA_PREFIX}/FACT_Transaction.csv"
trucks_dim_s3_key = f"{S3_MASTER_DATA_PREFIX}/DIM_Truck.csv"
payment_methods_dim_s3_key = f"{S3_MASTER_DATA_PREFIX}/DIM_Payment_Method.csv"

CLEAN_DATA_LOCAL_DIR = Path("../priv_clean_data")


def file_exists_in_s3(s3_key: str) -> bool:
    """Check if the specified file exists in S3."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        logger.info(f"S3 object exists: s3://{S3_BUCKET_NAME}/{s3_key}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.error(f"S3 object not found: s3://{S3_BUCKET_NAME}/{s3_key}")
        else:
            logger.error(f"Error checking S3 object: {e}")
        return False


def read_csv_from_s3(s3_key: str) -> pd.DataFrame:
    """Read a CSV file from S3 into a DataFrame."""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        df = pd.read_csv(io.BytesIO(response['Body'].read()))
        logger.info(f"Loaded {len(df)} rows from S3: s3://{S3_BUCKET_NAME}/{s3_key}")
        return df
    except ClientError as e:
        logger.error(f"Error reading S3 object: {e}")
        raise


def is_dataframe_empty(df: pd.DataFrame, df_name: str) -> bool:
    """Check if the specified DataFrame is empty."""
    if df.empty:
        logger.error(f"DataFrame is empty: {df_name}")
        return True
    logger.info(f"DataFrame is not empty: {df_name}")
    return False


def transactions_has_valid_trucks(trucks: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    is_valid = transactions["truck_id"].isin(trucks["truck_id"])
    logger.info(
        f"Filtering out {len(transactions) - is_valid.sum()} transactions with inexistent trucks")
    valid_transactions = transactions[is_valid]
    logger.info(
        f"Returning {len(valid_transactions)} valid transactions out of {len(transactions)}")
    return valid_transactions


def transactions_has_required_fields(transactions: pd.DataFrame) -> pd.DataFrame:
    """Filter out transactions missing any required fields: transaction_id, truck_id, payment_method_id, total, at"""
    required_fields = ["transaction_id", "truck_id",
                       "payment_method_id", "total", "at"]

    initial_count = len(transactions)

    # Check for null/missing values in required fields
    mask_has_all_fields = ~transactions[required_fields].isnull().any(axis=1)

    removed_count = initial_count - mask_has_all_fields.sum()
    logger.info(
        f"Filtering out {removed_count} transactions with missing required fields")

    valid_transactions = transactions[mask_has_all_fields].copy()
    logger.info(
        f"Returning {len(valid_transactions)} valid transactions out of {initial_count}")

    return valid_transactions


def transactions_has_valid_payment_method(transactions: pd.DataFrame, payment_methods: pd.DataFrame) -> pd.DataFrame:
    """ if payment method is 1 then it will work for 0 but if it is 0 it will not work for 1 """
    is_valid_method = transactions["payment_method_id"].isin(
        payment_methods["payment_method_id"])
    logger.info(
        f"Filtering out {len(transactions) - is_valid_method.sum()} invalid transactions with invalid payment method")
    valid_transactions = transactions[is_valid_method]

    truck_6_has_no_card_reader = (transactions["truck_id"] == 6) & (
        transactions["payment_method_id"] == 2
    )
    logger.info(
        f"Filtering out {truck_6_has_no_card_reader.sum()} transactions with no card reader but card payment occured")
    transactions["is_valid"] = ~truck_6_has_no_card_reader

    logger.info(
        f"Returning {len(valid_transactions)} valid transactions out of {len(transactions)}")
    return valid_transactions


def transactions_has_valid_total(transactions: pd.DataFrame) -> pd.DataFrame:
    """Filter out transactions with invalid total amounts."""

    if not isinstance(transactions["total"].iloc[0], (int, float)):
        logger.warning(
            "The 'total' column contains non-numeric values. They will be filtered out.")
        transactions["total"] = pd.to_numeric(
            transactions["total"], errors='coerce')

    transactions_under_zero = transactions["total"] >= 0
    transactions_not_valid = transactions["total"].apply(
        lambda x: isinstance(x, (int, float)))
    logger.info(
        f"Filtering out {len(transactions) - (transactions_under_zero & transactions_not_valid).sum()} transactions with invalid amounts")

    valid_transactions = transactions[transactions_under_zero &
                                      transactions_not_valid]
    logger.info(
        f"Returning {len(valid_transactions)} valid transactions out of {len(transactions)}")
    return valid_transactions


def transform() -> None:

    logger.info("Starting the transformation process")

    if not file_exists_in_s3(trucks_dim_s3_key):
        return
    if not file_exists_in_s3(transactions_fact_s3_key):
        return
    if not file_exists_in_s3(payment_methods_dim_s3_key):
        return

    try:
        trucks = read_csv_from_s3(trucks_dim_s3_key)
        transactions = read_csv_from_s3(transactions_fact_s3_key)
        payment_methods = read_csv_from_s3(payment_methods_dim_s3_key)
    except Exception as e:
        logger.error(f"Error loading CSV files from S3: {e}")
        return

    # Check if any of the loaded DataFrames are empty before proceeding

    if is_dataframe_empty(trucks, "trucks"):
        return
    logger.info("Trucks exist")
    if is_dataframe_empty(transactions, "transactions"):
        return
    logger.info("Transactions exist")
    if is_dataframe_empty(payment_methods, "payment_methods"):
        return
    logger.info("Payment methods exist")

    transactions["at"] = pd.to_datetime(transactions["at"], errors='coerce')

    logger.info(
        f"Loaded {len(trucks)} trucks and {len(transactions)} transactions")

    valid_transactions = transactions_has_required_fields(transactions)
    valid_transactions = transactions_has_valid_payment_method(
        valid_transactions, payment_methods)
    valid_transactions = transactions_has_valid_trucks(
        trucks, valid_transactions)
    valid_transactions = transactions_has_valid_total(valid_transactions)

    logger.info(f"Final valid transactions count: {len(valid_transactions)}")

    output_path = Path("../priv_clean_data/FACT_Transactions.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    valid_transactions.to_csv(output_path, index=False)
    logger.info(
        "Valid transactions have been saved to ../priv_clean_data/FACT_Transactions.csv")


if __name__ == "__main__":
    transform()
