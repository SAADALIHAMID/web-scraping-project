import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.signalmanager import dispatcher
from scrapy import signals
import re
import time
import logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
import streamlit as st
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Email extraction function
def extract_emails(html_content):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(email_pattern, html_content)))

# Enhanced Scrapy Spider for comprehensive crawling and email extraction
class EnhancedEmailSpider(scrapy.Spider):
    name = "enhanced_email_spider"

    custom_settings = {
        'CONCURRENT_REQUESTS': 10,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 5,
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_DELAY': 1,
        'DEPTH_LIMIT': 3,
        'FEED_FORMAT': 'json',
        'FEED_URI': 'output.json'
    }

    def __init__(self, start_url, **kwargs):
        self.start_urls = [start_url]
        self.allowed_domains = [start_url.split("//")[-1].split("/")[0]]
        self.emails = set()
        self.visited_pages = set()
        super().__init__(**kwargs)

    def parse(self, response):
        # Mark page as visited
        self.visited_pages.add(response.url)

        # Extract emails from the page
        emails = extract_emails(response.text)
        self.emails.update(emails)

        # Extract internal links
        for link in response.css('a::attr(href)').getall():
            if link.startswith('/'):
                link = response.urljoin(link)
            if link.startswith('http') and self.allowed_domains[0] in link and link not in self.visited_pages:
                yield scrapy.Request(link, callback=self.parse)

        # Check for specific pages based on keywords
        if any(keyword in response.url.lower() for keyword in ['contact', 'about', 'write-for-us', 'support']):
            emails = extract_emails(response.text)
            self.emails.update(emails)

# Function to run Scrapy for a single website
def run_scrapy_for_website(url):
    emails = set()
    process = CrawlerProcess(settings={"LOG_LEVEL": "ERROR"})

    def collect_emails(sender, item, response, spider):
        emails.update(spider.emails)

    dispatcher.connect(collect_emails, signal=signals.spider_closed)

    process.crawl(EnhancedEmailSpider, start_url=url)
    process.start()  # Blocking call
    return emails

# Selenium-based scraper for dynamic websites
def scrape_with_selenium(url):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(url)
        time.sleep(3)
        html_content = driver.page_source
        emails = extract_emails(html_content)
        return emails
    except Exception as e:
        logging.error(f"Error scraping {url} with Selenium: {e}")
        return []
    finally:
        driver.quit()

# Hybrid scraper to decide between Scrapy and Selenium
def scrape_with_hybrid(url, use_selenium):
    if use_selenium:
        return scrape_with_selenium(url)
    else:
        return run_scrapy_for_website(url)

# Function to normalize URLs input
def normalize_urls(input_text):
    urls = [url.strip() for url in re.split(r'[,\s]+', input_text) if url.strip()]
    return urls

# Function to scrape multiple websites with progress tracking
def scrape_multiple_websites(urls, use_selenium):
    results = []
    for url in tqdm(urls, desc="Scraping websites"):
        start_time = time.time()
        try:
            emails = scrape_with_hybrid(url, use_selenium)
            elapsed_time = time.time() - start_time
            result = {
                "Website": url,
                "Emails": ", ".join(emails),
                "Time Taken (s)": round(elapsed_time, 2),
            }
            results.append(result)
        except Exception as e:
            logging.error(f"Failed to scrape {url}: {e}")
            results.append({
                "Website": url,
                "Emails": "Error scraping website",
                "Time Taken (s)": "N/A",
            })
    return results

# Streamlit app
def main():
    st.title("Deep Website Email Scraper")
    st.markdown(
        "This app deeply scrapes **emails** from multiple websites and saves the results in a CSV file. "
        "You can enter URLs directly (even without commas) or upload a file."
    )

    # File uploader
    file = st.file_uploader("Upload a CSV/Excel file with website URLs", type=["csv", "xlsx"])
    urls_input = st.text_area(
        "Or enter websites (separated by commas, spaces, or newlines):",
        """https://www.brandveda.in/
https://www.namasteui.com/
https://www.justlittlethings.co.uk/
https://www.facebook.com/
https://www.healthyjeenasikho.com/
https://appdevelopmentcompanies.co/"""
    )
    use_selenium = st.checkbox("Use Selenium for dynamic content?")
    start_button = st.button("Start Scraping")

    if start_button:
        urls = []
        if file:
            ext = os.path.splitext(file.name)[1]
            if ext == ".csv":
                df = pd.read_csv(file)
            elif ext == ".xlsx":
                df = pd.read_excel(file)
            else:
                st.error("Unsupported file type!")
                return
            urls = df.iloc[:, 0].dropna().tolist()

        if urls_input:
            urls += normalize_urls(urls_input)

        if not urls:
            st.error("Please provide at least one valid URL.")
            return

        st.write(f"Scraping {len(urls)} websites...")
        results = scrape_multiple_websites(urls, use_selenium)

        df = pd.DataFrame(results)
        st.success("Scraping complete!")
        st.write("Extracted Emails:")
        st.dataframe(df)

        st.download_button(
            label="Download Results as CSV",
            data=df.to_csv(index=False),
            file_name="scraped_emails.csv",
            mime="text/csv",
        )

if __name__ == "__main__":
    main()