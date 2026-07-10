import subprocess
import sys
import csv
import pandas as pd


script_path = r"C:\Users\User\Downloads\files\deep_crawl.py"

df = pd.read_csv("20_customers_with_website.csv", sep="|")


for index, row in df.iterrows():
    url = row["website_url"]
    if url == "UNKNOWN" or pd.isna(url):
        continue  # skip rows without a real URL
    
    print(f"Crawling: {url}")
    result = subprocess.run(
        [sys.executable, script_path,"--customer_name", row["customer_name"], "--website_url", row["website_url"]],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error crawling {row["website_url"]}: {result.stderr}")