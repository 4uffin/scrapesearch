# scrapesearch.py
# A versatile command-line tool for web scraping search results from multiple search engines.
# It supports parallel scraping, configurable settings, and multiple output formats.

import requests
from bs4 import BeautifulSoup
import random
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time
import csv
import os
import sys
import re

# --- Configuration and Settings ---
# A list of domains to skip during scraping.
DOMAINS_TO_SKIP = [
    "twitter.com"
]

# A list of User-Agent strings to randomly choose from.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:107.0) Gecko/20100101 Firefox/107.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/108.0.1462.42 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 16_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1"
]

DEFAULT_CONFIG = {
    "num_urls": 5,
    "timeout": 10,
    "max_workers": 5,
    "retries": 3,
    "output_format": "json",
    "output_fields": ["url", "title", "description", "full_content"],
    "search_engine": "google"
}

SEARCH_ENGINES = {
    "google": {
        "url": "https://www.google.com/search?q=",
        "selectors": {
            "result_link_container": "div.tF2Cxc",
            "link": "a",
            "title": "h3",
            "snippet_container": "div.IsZz3e"
        }
    },
    "bing": {
        "url": "https://www.bing.com/search?q=",
        "selectors": {
            "result_link_container": "li.b_algo",
            "link": "h2 a",
            "title": "h2",
            "snippet_container": "div.b_caption p"
        }
    },
    "duckduckgo": {
        "url": "https://duckduckgo.com/html/?q=",
        "selectors": {
            "result_link_container": "div.results_links_deep",
            "link": "a.result__a",
            "title": "h2",
            "snippet_container": "a.result__snippet"
        }
    }
}

def load_config(filename="config.json"):
    """Loads configuration from a JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error reading config file: {e}. Using default settings.")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

# --- Core Functions ---
def clean_text(text):
    """Cleans up text by removing extra whitespace and newlines."""
    if not isinstance(text, str):
        return ""
    text = ' '.join(text.split())
    return text.strip()

def fetch_search_results(query, search_engine, timeout_seconds, retries):
    """
    Fetches search results from a specified search engine with retries.
    """
    if search_engine not in SEARCH_ENGINES:
        print(f"Error: Unsupported search engine '{search_engine}'. Using 'google' instead.")
        search_engine = "google"
    
    engine_config = SEARCH_ENGINES[search_engine]
    search_url = f"{engine_config['url']}{query}"
    selectors = engine_config['selectors']

    for attempt in range(retries):
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            response = requests.get(search_url, headers=headers, allow_redirects=True, timeout=timeout_seconds)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            result_links = soup.select(selectors['result_link_container'])
            
            results = []
            if result_links:
                for link_container in result_links:
                    link = link_container.select_one(selectors['link'])
                    title_elem = link_container.select_one(selectors['title'])
                    snippet_elem = link_container.select_one(selectors['snippet_container'])
                    
                    link_href = link.get('href') if link else None
                    title_text = title_elem.text if title_elem else "No title found"
                    snippet_text = snippet_elem.text if snippet_elem else "No snippet found"
                    
                    if link_href and title_text:
                        results.append({
                            "url": link_href,
                            "title": clean_text(title_text),
                            "snippet": clean_text(snippet_text)
                        })
                return results
            else:
                print(f"No main search results found for {search_engine}.")
                return []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [500, 503]:
                print(f"Server error ({e.response.status_code}) on attempt {attempt + 1}. Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"An HTTP error occurred: {e}")
                return []
        except requests.exceptions.Timeout:
            print(f"Timeout occurred on attempt {attempt + 1}. Retrying...")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching search results: {e}")
            return []
    
    print(f"Failed to fetch search results after {retries} attempts.")
    return []

def scrape_page(url, verbose, timeout_seconds, retries):
    """
    Scrapes information from a given URL with retries.
    """
    for domain in DOMAINS_TO_SKIP:
        if domain in url:
            if verbose:
                print(f"\nSkipping {domain} page: {url}")
            return None
    
    for attempt in range(retries):
        try:
            if verbose:
                print(f"\nScraping page: {url} (Attempt {attempt + 1})")
                
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            response = requests.get(url, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            page_title = soup.title.get_text(strip=True) if soup.title else "No title found"
            meta_description = soup.find("meta", attrs={"name": "description"})
            page_description = meta_description["content"] if meta_description else "No description found"
            
            # More intelligent content extraction
            # Find the main content area and exclude common non-content elements
            main_content_tags = soup.find('main') or soup.find('article') or soup.body
            
            if main_content_tags:
                # Remove common irrelevant tags before extracting text
                for tag in main_content_tags.find_all(['header', 'footer', 'nav', 'aside', 'script', 'style']):
                    tag.decompose()
                
                content_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
                page_contents = " ".join([tag.get_text(strip=True) for tag in main_content_tags.find_all(content_tags)])
            else:
                page_contents = "No content found in main tags."

            if verbose:
                print(f"Page title: {clean_text(page_title)}")
                print(f"Page description: {clean_text(page_description)}")
                print(f"Page content snippet: {clean_text(page_contents)[:200]}...")
                
            return {
                "url": url,
                "title": clean_text(page_title),
                "description": clean_text(page_description),
                "full_content": clean_text(page_contents)
            }
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"Error while scraping {url}: {e} on attempt {attempt + 1}")
            time.sleep(2 ** attempt)
        except Exception as e:
            if verbose:
                print(f"An unexpected error occurred while scraping {url}: {e}")
            return None
    
    if verbose:
        print(f"Failed to scrape {url} after {retries} attempts.")
    return None

def save_to_json(data, filename):
    """Saves a list of dictionaries to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully saved scraped data to {filename}")
    except Exception as e:
        print(f"An error occurred while saving the JSON file: {e}")

def save_to_csv(data, filename, fields):
    """Saves a list of dictionaries to a CSV file."""
    if not data:
        print("\nNo data to save.")
        return
    
    try:
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
        print(f"\nSuccessfully saved scraped data to {filename}")
    except Exception as e:
        print(f"An error occurred while saving the CSV file: {e}")

def sanitize_filename(query):
    """Creates a safe filename from a query string by replacing invalid characters with underscores."""
    # Replaces any sequence of characters that are not alphanumeric, spaces, or hyphens with a single underscore.
    safe_name = re.sub(r'[^\w\s-]', '_', query).strip()
    # Replaces any remaining spaces with underscores.
    safe_name = re.sub(r'\s+', '_', safe_name)
    return safe_name

# --- Main Execution Modes ---
def process_scraped_data(scraped_data, fields):
    """
    Filters scraped data to include only the specified fields and performs validation.
    An item is only considered invalid if the 'url' field is missing.
    """
    processed_data = []
    for item in scraped_data:
        # We only filter out items if the URL is missing, as other fields
        # might be legitimately empty but the data is still useful.
        if item.get('url'):
            filtered_item = {field: item.get(field) for field in fields if field in item}
            # Fill in missing fields with a placeholder to maintain structure
            for field in fields:
                if field not in filtered_item:
                    filtered_item[field] = "Field not found"
            processed_data.append(filtered_item)
    return processed_data

def process_single_query(query, args, config):
    """Processes a single search query and its scraping tasks."""
    print(f"Processing query: '{query}'")
    # The search engine is determined by the config, which can be overridden by the CLI arg
    search_engine = args.engine if args.engine else config.get('search_engine', 'google')
    results = fetch_search_results(query, search_engine, config["timeout"], config["retries"])
    
    if args.search_only:
        print("\nSearch results (not scraping):")
        for i, result in enumerate(results[:config["num_urls"]]):
            print(f"{i+1}. {result['title']} - {result['url']}")
        return []
    
    scraped_data = []
    if results:
        urls_to_scrape = random.sample(results, min(config["num_urls"], len(results)))
        
        with ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
            future_to_url = {executor.submit(scrape_page, url['url'], args.verbose, config["timeout"], config["retries"]): url['url'] for url in urls_to_scrape}
            
            for future in tqdm(as_completed(future_to_url), total=len(urls_to_scrape), desc=f"Scraping '{query}'"):
                scraped_result = future.result()
                if scraped_result:
                    scraped_data.append(scraped_result)
    
    return scraped_data

def cli_mode(args, config):
    """Handles the command-line interface mode of the script."""
    all_scraped_data = []

    if args.input_file:
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                queries = [line.strip() for line in f if line.strip()]
            
            if not queries:
                print("Input file is empty. Exiting.")
                return

            print(f"Found {len(queries)} queries in '{args.input_file}'.")
            
            for query in queries:
                scraped_results = process_single_query(query, args, config)
                processed_data = process_scraped_data(scraped_results, config["output_fields"])
                
                if processed_data:
                    if args.per_query_output:
                        filename = f"{sanitize_filename(query)}.{config['output_format']}"
                        if config['output_format'] == 'json':
                            save_to_json(processed_data, filename)
                        elif config['output_format'] == 'csv':
                            save_to_csv(processed_data, filename, config['output_fields'])
                    else:
                        all_scraped_data.extend(processed_data)
                
                print("-" * 50)
            
        except FileNotFoundError:
            print(f"Error: The file '{args.input_file}' was not found.")
            return
        except Exception as e:
            print(f"An error occurred while reading the input file: {e}")
            return
    elif args.query:
        scraped_results = process_single_query(args.query, args, config)
        all_scraped_data.extend(process_scraped_data(scraped_results, config["output_fields"]))
    else:
        print("Please provide a search query or an input file.")
        return
    
    if all_scraped_data:
        # Use the provided output file name, but ensure the correct extension.
        # This logic is simpler and more readable.
        if args.output_file:
            base, ext = os.path.splitext(args.output_file)
            filename = f"{base}.{config['output_format']}"
        else:
            filename = f"scraped_results.{config['output_format']}"

        if config['output_format'] == 'json':
            save_to_json(all_scraped_data, filename)
        elif config['output_format'] == 'csv':
            save_to_csv(all_scraped_data, filename, config['output_fields'])
        
        print(f"\nSummary: Successfully scraped a total of {len(all_scraped_data)} pages.")
    elif not args.per_query_output and not all_scraped_data:
        print("\nNo data was successfully scraped.")

def interactive_mode(args, config):
    """Handles the interactive mode of the script."""
    while True:
        try:
            query = input("Welcome to ScrapeSearch\n\nEnter your search query (or 'quit' to exit): ")
            if query.lower() == "quit":
                break
            
            scraped_data = process_single_query(query, args, config)
            
            if scraped_data:
                processed_data = process_scraped_data(scraped_data, config["output_fields"])
                
                if not processed_data:
                    print("No valid data was scraped for this query.")
                    continue

                output_choice = input("\nWould you like to save the results to a file? (y/n): ")
                if output_choice.lower() == 'y':
                    format_choice = input(f"Enter output format (json/csv), default is '{config['output_format']}': ")
                    final_format = format_choice.lower() if format_choice in ['json', 'csv'] else config['output_format']
                    
                    fields_choice = input(f"Enter output fields (comma-separated, default is '{','.join(config['output_fields'])}'): ")
                    final_fields = [f.strip() for f in fields_choice.split(',')] if fields_choice else config['output_fields']
                    
                    save_per_query = input("Save to a file named after the query? (y/n): ")
                    if save_per_query.lower() == 'y':
                        filename = f"{sanitize_filename(query)}.{final_format}"
                    else:
                        filename = input("Enter a filename (e.g., 'my_results'): ")
                        if filename == '':
                            filename = 'my_results'
                        if not filename.endswith(f".{final_format}"):
                            filename = f"{os.path.splitext(filename)[0]}.{final_format}"

                    if final_format == 'json':
                        save_to_json(processed_data, filename)
                    elif final_format == 'csv':
                        save_to_csv(processed_data, filename, final_fields)
        except KeyboardInterrupt:
            print("\n\nScript interrupted. Exiting gracefully.")
            sys.exit(0)

def main():
    """Main function to parse arguments and run the correct mode."""
    parser = argparse.ArgumentParser(description="Scrape search results from Google.")
    
    # Argument group for general options
    general_group = parser.add_argument_group("General Options")
    general_group.add_argument("query", nargs="?", help="The search query to use.")
    general_group.add_argument("-i", "--input-file", help="Path to a text file with a list of queries.")
    general_group.add_argument("-o", "--output-file", help="Name of the output file to save results (for single query or combined batch output).")
    general_group.add_argument("-p", "--per-query-output", action="store_true",
                               help="Save results for each query in the input file to a separate file.")
    general_group.add_argument("-e", "--engine", choices=SEARCH_ENGINES.keys(),
                               help="The search engine to use (e.g., 'google', 'bing', 'duckduckgo').")
    general_group.add_argument("-f", "--format", choices=['json', 'csv'],
                               help="The output format for the scraped data.")
    general_group.add_argument("-F", "--fields",
                               help="Comma-separated list of fields to save (e.g., 'url,title').")
    general_group.add_argument("-v", "--verbose", action="store_true",
                               help="Enable verbose output for scraping status.")
    general_group.add_argument("--config", default="config.json",
                               help="Path to a custom configuration file (default: config.json).")

    # Argument group for performance tuning
    performance_group = parser.add_argument_group("Performance Tuning")
    performance_group.add_argument("-n", "--num-urls", type=int,
                                   help="Number of URLs to scrape.")
    performance_group.add_argument("-t", "--timeout", type=int,
                                   help="Timeout for each HTTP request in seconds.")
    performance_group.add_argument("-w", "--max-workers", type=int,
                                   help="Maximum number of concurrent workers for scraping.")

    # Argument for search-only mode
    parser.add_argument("-s", "--search-only", action="store_true",
                        help="Only perform a search and list the results, do not scrape.")
    
    args = parser.parse_args()
    
    # Load config and override with command-line arguments if provided
    config = load_config(args.config)
    if args.num_urls is not None:
        config["num_urls"] = args.num_urls
    if args.timeout is not None:
        config["timeout"] = args.timeout
    if args.max_workers is not None:
        config["max_workers"] = args.max_workers
    if args.format is not None:
        config["output_format"] = args.format
    if args.fields is not None:
        config["output_fields"] = [f.strip() for f in args.fields.split(',')]
    if args.engine is not None:
        config["search_engine"] = args.engine

    # Check for mutually exclusive arguments
    if args.query and args.input_file:
        parser.error("Arguments 'query' and '-i/--input-file' are mutually exclusive. Please use one or the other.")

    try:
        if args.query or args.input_file:
            cli_mode(args, config)
        else:
            interactive_mode(args, config)
    except KeyboardInterrupt:
        print("\n\nScript interrupted. Exiting gracefully.")
        sys.exit(0)

if __name__ == "__main__":
    main()
