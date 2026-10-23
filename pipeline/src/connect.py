"""Database connection utility for MySQL."""
import sys
from os import environ

import pymysql
from dotenv import load_dotenv
from logger import setup_logger

logger = setup_logger()
load_dotenv()


def get_connection():
    """Establish and return a connection to the MySQL database."""
    return pymysql.connect(
        host=environ["DB_HOST"],
        user=environ["DB_USER"],
        password=environ["DB_PASSWORD"],
        database=environ["DB_NAME"],
        port=int(environ["DB_PORT"]),
        cursorclass=pymysql.cursors.DictCursor
    )


def check_connection() -> None:
    """Check if the database connection is valid."""
    query = """
    SELECT 1;
    """
    connection = get_connection()

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    if len(rows) <= 0:
        raise ConnectionError("Failed to verify the database connection.")


if __name__ == "__main__":
    try:
        logger.info("Checking database connection.")
        check_connection()
        logger.info("Database connection verified successfully.")
    except ConnectionError as e:
        logger.error("Connection failed: %s", e)
        sys.exit(1)
