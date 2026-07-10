import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    DomainFilter,
    URLPatternFilter,
    ContentTypeFilter
)
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
import boto3
import time
import argparse
import sys
import re

parser = argparse.ArgumentParser()
parser.add_argument("--website_url", required=True)
parser.add_argument("--customer_name", required=True)
args = parser.parse_args()

print(f"customer name: {args.customer_name}, website url: {args.website_url}")  # Website Url


def replace_spaces(text):
    return re.sub(r"\s+", "_", text)

# sys.exit()

async def run_advanced_crawler():
    # Create a sophisticated filter chain
    filter_chain = FilterChain([
        # Domain boundaries
        DomainFilter(
            allowed_domains=[args.website_url]
            # blocked_domains=["old.docs.example.com"]
        ),

        # URL patterns to include
        URLPatternFilter(patterns=["*operations*", "*what-we-do*", "*about*", "*operation*","*countries*", "*country*","*location*", "*operate*"]),

        # Content type filtering
        ContentTypeFilter(allowed_types=["text/html"])
    ])

    # Create a relevance scorer
    keyword_scorer = KeywordRelevanceScorer(
        keywords=["operations", "what-we-do", "locations","operation", "countries", "about", "country", "operate"],
        weight=0.7
    )

    # Set up the configuration
    config = CrawlerRunConfig(
        deep_crawl_strategy=BestFirstCrawlingStrategy(
            max_depth=3,
            include_external=False,
            filter_chain=filter_chain,
            url_scorer=keyword_scorer
        ),
        scraping_strategy=LXMLWebScrapingStrategy(),
        stream=True,
        verbose=True
    )

    # Execute the crawl
    results = []
    results_urls = []
    async with AsyncWebCrawler() as crawler:
        async for result in await crawler.arun(args.website_url, config=config):
            results.append(result)
            results_urls.append(result.url)
            score = result.metadata.get("score", 0)
            depth = result.metadata.get("depth", 0)
            print(f"Depth: {depth} | Score: {score:.2f} | {result.url}")

    # Analyze the results
    print(f"Crawled {len(results)} high-value pages")
    # print(f"The urls crawled: {results_urls}")
    print(f"Average score: {sum(r.metadata.get('score', 0) for r in results) / len(results):.2f}")

    # Group by depth
    depth_counts = {}
    for result in results:
        file_name = replace_spaces(args.customer_name)
        with open(f"./data/{file_name}.md", "a", encoding="utf-8") as f:
            f.write(result.markdown)

        depth = result.metadata.get("depth", 0)
        depth_counts[depth] = depth_counts.get(depth, 0) + 1
    
    time.sleep(3)
    s3 = boto3.client('s3')
    s3.upload_file(f"./data/{file_name}.md", 'locations-source-data', f"md_files/{file_name}.md")

    print("Pages crawled by depth:")
    for depth, count in sorted(depth_counts.items()):
        print(f"  Depth {depth}: {count} pages")

if __name__ == "__main__":
    asyncio.run(run_advanced_crawler())
