import boto3
from botocore.exceptions import ClientError
from logger import setup_logger

logger = setup_logger()

CRAWLER_NAME = "c26-aloysius-t3-crawler"
REGION = "eu-west-2"


def crawl():
    """Crawl the S3 bucket using an AWS Glue crawler."""
    logger.info("Initialising AWS Glue client.")
    glue_client = boto3.client("glue", region_name=REGION)

    try:
        # Check current crawler status
        crawler_info = glue_client.get_crawler(Name=CRAWLER_NAME)
        state = crawler_info.get("Crawler", {}).get("State")

        if state == "RUNNING":
            logger.info(
                "Crawler '%s' is currently running. Stopping crawler...", CRAWLER_NAME)
            glue_client.stop_crawler(Name=CRAWLER_NAME)
            logger.info(
                "Stop signal sent successfully to crawler '%s'.", CRAWLER_NAME)
            return

        # Start crawler if not currently running
        response = glue_client.start_crawler(Name=CRAWLER_NAME)

        if response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
            logger.info("Crawler '%s' started successfully.", CRAWLER_NAME)
        else:
            logger.error("Failed to start crawler '%s'.", CRAWLER_NAME)

    except ClientError as e:
        logger.error("Error communicating with AWS Glue: %s", e)


if __name__ == "__main__":
    crawl()
