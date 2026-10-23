""" Combines extract, transform, and load operations. """

import sys

from logger import setup_logger
from extract import extract
from transform import transform
from load import load
from connect import check_connection
from crawl import crawl

logger = setup_logger()


def run_extraction() -> None:
    """Execute the extraction phase of the pipeline."""
    logger.info("=" * 50)
    logger.info("STARTING EXTRACTION PHASE")
    logger.info("=" * 50)

    try:
        logger.info("Checking database connection.")
        check_connection()
        logger.info("Database connection verified successfully.")
    except ConnectionError as e:
        logger.error("Connection failed: %s", e)
        raise

    if extract():
        logger.info("New transactions extracted successfully.")
    else:
        logger.info("No new transactions to extract.")
        logger.info("PIPELINE TERMINATED EARLY DUE TO NO NEW TRANSACTIONS.")
        logger.info("=" * 50)
        sys.exit(0)

    logger.info("=" * 50)
    logger.info("EXTRACTION PHASE COMPLETED")
    logger.info("=" * 50)


def run_transformation() -> None:
    """Execute the transformation phase of the pipeline."""
    logger.info("=" * 50)
    logger.info("STARTING TRANSFORMATION PHASE")
    logger.info("=" * 50)

    transform()

    logger.info("=" * 50)
    logger.info("TRANSFORMATION PHASE COMPLETED")
    logger.info("=" * 50)


def run_loading() -> None:
    """Execute the loading phase of the pipeline."""
    logger.info("=" * 50)
    logger.info("STARTING LOADING PHASE")
    logger.info("=" * 50)

    load()

    logger.info("=" * 50)
    logger.info("LOADING PHASE COMPLETED")
    logger.info("=" * 50)


def run_crawl() -> None:
    """Execute the crawl phase after loading."""
    logger.info("=" * 50)
    logger.info("STARTING CRAWL PHASE")
    logger.info("=" * 50)

    try:
        crawl()
        logger.info("Crawler initiated successfully.")
    except Exception as e:
        logger.error("Crawl failed with error: %s", e)
        raise

    logger.info("=" * 50)
    logger.info("CRAWL PHASE COMPLETED")
    logger.info("=" * 50)


def run_pipeline() -> None:
    """Execute the complete ETL pipeline."""
    logger.info("\n")
    logger.info("#" * 50)
    logger.info("# STARTING COMPLETE ETL PIPELINE")
    logger.info("#" * 50)

    try:
        run_extraction()
        run_transformation()
        run_loading()
        run_crawl()

        logger.info("#" * 50)
        logger.info("# ETL PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("#" * 50)
        logger.info("\n")

    except Exception as e:
        logger.error("Pipeline failed with error: %s", e)
        logger.error("#" * 50)
        logger.error("# ETL PIPELINE FAILED")
        logger.error("#" * 50)
        raise


if __name__ == "__main__":
    run_pipeline()
