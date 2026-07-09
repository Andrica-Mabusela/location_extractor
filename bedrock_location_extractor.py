"""
bedrock_location_extractor.py

Queries an AWS Bedrock Nova Pro model to extract physical locations
associated with a given company name, returning structured CSV data.

Usage:
    python bedrock_location_extractor.py

Requires:
    boto3
    AWS credentials configured (via ~/.aws/credentials, env vars, or IAM role)
    Bedrock model access enabled for amazon.nova-pro-v1:0 in your AWS account/region
"""

import boto3
import json
import csv
import io
import logging
from typing import Optional
import sys

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# Config
DEFAULT_MODEL_ID = "amazon.nova-pro-v1:0"
DEFAULT_REGION = "us-east-1"  # change to your Bedrock-enabled region

EXPECTED_COLUMNS = ['customer_name','address','country','type_of_operation']


def build_grounded_prompt(customer_name: str, website_url: str) -> str:
    """
    Builds the grounded extraction prompt for a given customer name and website.
    """
    prompt = f"""You are a research specialist in Geospatial area.
        TASK 
        Given the customer name "{customer_name}", identify all physical locations associated with the customer, their website is "{website_url}, crawl the {customer_name} to find the physical location addresses".
        A physical addresses includes:

        * Head offices
        * Corporate offices
        * Regional offices
        * Branches
        * Stores
        * Warehouses"
        * Distribution centres
        * Manufacturing plants
        * Factories
        * Mines
        * Processing plants
        * Smelters
        * Refineries
        * Operational sites
        * Depots
        * Research facilities
        For each physical address, extract:

        1. customer_name
        2. address
        3. country
        4. type_of_operation

        OUTPUT REQUIREMENTS:
        Return ONLY CSV format.
        Columns must be:
        'customer_name','address','country','type_of_operation'
        Rules:

        * One location per row.
        * Do not aggregate multiple locations into a single row.
        * Preserve official names where available.
        * Use country names in full.
        * Use the most specific location available.
        * Remove duplicates.
        * Do not include commentary.
        * Do not include markdown.
        * Do not include explanations.
        * If country cannot be determined, use UNKNOWN.
        * Do not include any extra columns other than what I sepcified for you to extract"""
    return prompt


def query_bedrock_nova(
    customer_name: str,
    website_url: str,
    model_id: str = DEFAULT_MODEL_ID,
    region_name: str = DEFAULT_REGION,
    max_tokens: int = 512,  # The maximum number of tokens the model is allowed to generate in it's response
    temperature: float = 0.1,  # Temperature will control how random or creative the output is.
    top_p: float = 0.9,  # This is called Nucleus sampling, Instead of always considering every possible next token, the model only considers the smallest set of tokens whose cumulative probability reaches p.
    bedrock_client: Optional[boto3.client] = None,
) -> str:
    """
    Sends the grounded prompt to the Bedrock Nova Pro model and returns the
    raw text response (expected to be CSV).

    Uses the Bedrock Converse API, which Nova models support natively.
    """
    client = bedrock_client or boto3.client("bedrock-runtime", region_name=region_name)

    prompt = build_grounded_prompt(customer_name, website_url)

    logger.info("Querying %s for locations of '%s'", model_id, customer_name)

    response = client.converse(
        modelId=model_id,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        },
    )

    output_message = response["output"]["message"]
    text_parts = [
        block["text"] for block in output_message["content"] if "text" in block
    ]
    raw_text = "".join(text_parts).strip()

    return raw_text


def clean_csv_text(raw_text: str) -> str:
    """
    Strips common wrapping artifacts models sometimes add despite instructions
    (e.g. markdown code fences) before CSV parsing.
    """
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        # drop first line (``` or ```csv) and trailing ``` if present
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text


def parse_csv_rows(raw_text: str) -> list[dict]:
    """
    Parses the model's CSV output into a list of dicts, validating the
    expected header. Returns an empty list if parsing fails or output
    doesn't match the expected schema.
    """
    cleaned = clean_csv_text(raw_text)

    if not cleaned:
        logger.warning("Empty response from model.")
        return []

    reader = csv.DictReader(io.StringIO(cleaned),  delimiter="|")

    if reader.fieldnames is None:
        logger.warning("Could not parse CSV header from response.")
        return []

    normalized_fields = [f.strip().lower() for f in reader.fieldnames]
    if normalized_fields != EXPECTED_COLUMNS:
        logger.warning(
            "Unexpected CSV header: %s (expected %s)",
            reader.fieldnames,
            EXPECTED_COLUMNS,
        )
        # still attempt to return rows in case of minor casing/whitespace diffs

    rows = []
    for row in reader:
        # skip fully blank rows
        if not any((v or "").strip() for v in row.values()):
            continue
        print(row)
        rows.append({k.strip(): (v or "").strip() for k, v in row.items()})

    return rows


def extract_locations_to_csv_file(
    customer_name: str,
    website_url: str,
    output_path: str,
    model_id: str = DEFAULT_MODEL_ID,
    region_name: str = DEFAULT_REGION,
) -> list[dict]:
    """
    Full pipeline: query Bedrock, parse the CSV response, validate rows,
    and write results to output_path. Returns the parsed rows.
    """
    raw_text = query_bedrock_nova(
        customer_name=customer_name,
        website_url=website_url,
        model_id=model_id,
        region_name=region_name,
    )

    rows = parse_csv_rows(raw_text)

    if not rows:
        logger.warning(
            "No rows extracted for '%s'. Raw response:\n%s", customer_name, raw_text
        )
        return []

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS, delimiter="|")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "UNKNOWN") for col in EXPECTED_COLUMNS})

    logger.info("Wrote %d rows to %s", len(rows), output_path)
    return rows


if __name__ == "__main__":

    with open("customers.csv", mode="r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        companies = list(reader)

    all_rows = []
    for company in companies:
        rows = extract_locations_to_csv_file(
            customer_name=company["customer_name"],
            website_url=company["website_url"],
            output_path=f"customer_locations/{company['customer_name'].replace(' ', '_')}_locations.csv",
        )
        all_rows.extend(rows)

    logger.info("Total locations extracted across all companies: %d", len(all_rows))
