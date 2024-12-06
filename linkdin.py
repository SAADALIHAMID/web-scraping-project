import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from scrapy.selector import Selector
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import os
import time
from webdriver_manager.chrome import ChromeDriverManager

# Excluded domains and patterns (including social media and common footer links)
EXCLUDED_WEBSITES = [
    'facebook.com', 'instagram.com', 'twitter.com', 'youtube.com', 'linkedin.com',
    'forbes.com', 'amazon.com', 'pinterest.com', 'imdb.com', 'indeed.com', 'moz.com',
    'quora.com', 'semrush.com', 'google.com', 'google.org', 'bbc.co.uk', '.gov'
]
EXCLUDED_PATTERNS = ['#', '/contact', '/privacy', '/terms']

# Initialize Selenium WebDriver
def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")  # Ignore SSL certificate errors

    chrome_driver_path = ChromeDriverManager().install()
    return webdriver.Chrome(service=Service(chrome_driver_path), options=options)

# Extract outgoing links from a single webpage
def extract_links_from_page(url):
    outgoing_links = set()
    driver = None
    try:
        driver = init_driver()
        driver.get(url)
        time.sleep(3)  # Allow page to load fully

        page_source = driver.page_source
        selector = Selector(text=page_source)
        anchor_tags = selector.css('a::attr(href)').getall()

        parsed_url = urlparse(url)
        main_domain = parsed_url.netloc.replace('www.', '')

        for link in anchor_tags:
            full_url = urljoin(url, link)  # Convert relative URLs to absolute
            parsed_link = urlparse(full_url)
            domain = parsed_link.netloc.replace('www.', '')

            # Exclude main domain, subdomains, and predefined domains
            if (
                domain
                and main_domain not in domain
                and not any(excluded in domain for excluded in EXCLUDED_WEBSITES)
                and not any(pattern in full_url for pattern in EXCLUDED_PATTERNS)
            ):
                outgoing_links.add(f"https://{domain}/")
    except Exception as e:
        st.warning(f"Error processing {url}: {e}")
    finally:
        if driver:
            driver.quit()

    return list(outgoing_links)

# Process URLs concurrently
def process_urls_concurrently(urls):
    all_outgoing_links = {}
    with ThreadPoolExecutor(max_workers=5) as executor:  # Adjust thread count for performance
        future_to_url = {executor.submit(extract_links_from_page, url): url for url in urls}
        for future in future_to_url:
            url = future_to_url[future]
            try:
                all_outgoing_links[url] = future.result()
            except Exception as e:
                st.warning(f"Error processing {url}: {e}")
    return all_outgoing_links

# Save results to a CSV file
def save_to_csv(results):
    timestamp = int(time.time())
    filename = f"outgoing_links_{timestamp}.csv"

    rows = []
    for base_url, links in results.items():
        for link in links:
            rows.append({"Base URL": base_url, "Outgoing Link": link})

    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False)
    return filename

# Save results to an Excel file
def save_to_excel(results):
    timestamp = int(time.time())
    filename = f"outgoing_links_{timestamp}.xlsx"

    rows = []
    for base_url, links in results.items():
        for link in links:
            rows.append({"Base URL": base_url, "Outgoing Link": link})

    df = pd.DataFrame(rows)
    
    # Save as Excel
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Outgoing Links')
        workbook = writer.book
        worksheet = writer.sheets['Outgoing Links']
        
        # Add formatting for better readability
        worksheet.set_column('A:A', 30)  # Set column width for Base URL
        worksheet.set_column('B:B', 50)  # Set column width for Outgoing Link
        worksheet.freeze_panes(1, 0)  # Freeze the header row
    return filename

# Streamlit Web App
def main():
    st.title("Advanced Outgoing Links Fetcher")
    st.markdown("""
    **Welcome to the Outgoing Links Extractor!**  
    This tool allows you to extract external links from multiple URLs.  
    You can upload a list of URLs in either **CSV** or **Excel** format, or enter them manually.

    **How to use**:
    1. **Upload an Excel or CSV file**: The first column should contain URLs.
    2. **Enter multiple URLs manually** (comma-separated or line-separated).
    3. **Results**: Extracted external links will be displayed and can be downloaded in **CSV** or **Excel** format.
    """)

    # Sidebar for file upload and input options
    st.sidebar.header("Input Options")
    uploaded_file = st.sidebar.file_uploader("Upload an Excel or CSV file with URLs", type=['xlsx', 'csv'])
    urls_input = st.sidebar.text_area("Or enter URLs (comma-separated or line-separated):")

    submit_button = st.sidebar.button("Fetch Outgoing Links")

    urls = []

    # Process Excel or CSV file input
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
            
            urls.extend(df.iloc[:, 0].dropna().tolist())  # Assuming URLs are in the first column
        except Exception as e:
            st.error(f"Error reading the file: {e}")

    # Process manual text input
    if urls_input.strip():
        urls.extend([url.strip() for url in urls_input.replace(',', '\n').split('\n') if url.strip()])

    # Handle duplicates
    urls = list(set(urls))

    if submit_button:
        if not urls:
            st.warning("Please provide at least one URL (via text input or file upload).")
            return

        st.info(f"Processing {len(urls)} URLs. Please wait...")

        # Start progress spinner
        with st.spinner("Fetching outgoing links... This might take a while."):
            results = process_urls_concurrently(urls)

        if results:
            st.success("Processing complete!")
            st.subheader("Outgoing Links by Website:")

            # Display results dynamically
            for idx, (base_url, links) in enumerate(results.items()):
                st.write(f"### {base_url}")
                st.text_area(
                    "Outgoing Links",
                    value="\n".join(links),
                    height=200,
                    key=f"links_{idx}"  # Unique key for each text area
                )

            # Save to CSV and Excel, and provide download links
            csv_file = save_to_csv(results)
            excel_file = save_to_excel(results)

            # Provide download links for CSV and Excel
            with open(csv_file, "rb") as file:
                st.download_button(
                    label="Download CSV",
                    data=file,
                    file_name=csv_file,
                    mime="text/csv"
                )
            
            with open(excel_file, "rb") as file:
                st.download_button(
                    label="Download Excel",
                    data=file,
                    file_name=excel_file,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No outgoing links found.")
    else:
        st.warning("Please upload a file or enter URLs.")

if __name__ == "__main__":
    main()
