import requests
import feedparser
from datetime import datetime, timezone, timedelta
import subprocess
import time
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

TOPICS = [
    "unstructured data analysis",
    "querying unstructured data",
    "semi structured data",
    "text to table",
    "text to relational schema",
]
MAX_RESULTS = 10
MODEL = "gemma2:2b"  
DAYS_BACK = 7  # look back at last 7 days
VERBOSE = True
RELEVANT_PAPERS_FILE = "relevant_papers.txt"


USER_EMAIL = os.getenv("USER_EMAIL", "")  # Your email address
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")  # Gmail default
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # 587 for TLS
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")  # Usually same as USER_EMAIL
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Use app password for Gmail, NOT YOUR REGULAR PASSWORD

def extract_paper_id(entry) -> str:
    """Extract arXiv paper ID from entry (e.g., '1234.5678' from 'http://arxiv.org/abs/1234.5678v1')."""
    # entry.id typically looks like: http://arxiv.org/abs/1234.5678v1
    # or entry.link might be: http://arxiv.org/abs/1234.5678
    id_str = getattr(entry, 'id', getattr(entry, 'link', ''))
    # Extract the numeric part (e.g., 1234.5678)
    match = re.search(r'/(\d{4}\.\d{4,5})', id_str)
    if match:
        return match.group(1)
    # Fallback: try to extract any pattern that looks like an arXiv ID
    match = re.search(r'(\d{4}\.\d{4,5})', id_str)
    if match:
        return match.group(1)
    return None


def load_relevant_paper_ids(file_path: str) -> set:
    """Load existing relevant paper IDs from the txt file."""
    if not os.path.exists(file_path):
        if VERBOSE:
            print(f"[DEBUG] Cache file '{file_path}' does not exist, starting with empty cache")
        return set()
    
    paper_ids = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                paper_id = line.strip()
                if paper_id:  # Skip empty lines
                    paper_ids.add(paper_id)
        if VERBOSE:
            print(f"[DEBUG] Loaded {len(paper_ids)} paper IDs from cache file '{file_path}'")
    except Exception as e:
        print(f"[WARN] Failed to load cache file '{file_path}': {e}")
        if VERBOSE:
            print(f"[DEBUG] Exception details: {type(e).__name__}: {str(e)}")
    
    return paper_ids


def save_paper_id(file_path: str, paper_id: str):
    """Append a paper ID to the cache file."""
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"{paper_id}\n")
        if VERBOSE:
            print(f"[DEBUG] Saved paper ID '{paper_id}' to cache file '{file_path}'")
    except Exception as e:
        print(f"[WARN] Failed to save paper ID '{paper_id}' to cache file '{file_path}': {e}")
        if VERBOSE:
            print(f"[DEBUG] Exception details: {type(e).__name__}: {str(e)}")


def query_arxiv(keyword: str, max_results: int = 20):
    if VERBOSE:
        print(f"[DEBUG] Querying arXiv API for: '{keyword}' (max_results={max_results})")
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query=all:{keyword.replace(' ', '+')}"
        f"&start=0&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    if VERBOSE:
        print(f"[DEBUG] Request URL: {url}")
    start_time = time.time()
    resp = requests.get(url, timeout=15)
    elapsed = time.time() - start_time
    if VERBOSE:
        print(f"[DEBUG] API response received in {elapsed:.2f}s (status: {resp.status_code})")
    feed = feedparser.parse(resp.text)
    entry_count = len(feed.entries)
    if VERBOSE:
        print(f"[DEBUG] Parsed {entry_count} entries from feed")
    return feed.entries


def parse_llm_response(output: str) -> tuple[bool, str]:
    if not output:
        return False, "(empty)"
    
    words = output.strip().split()
    if not words:
        return False, "(empty)"
    
    first_word = words[0].strip().upper().rstrip('.,!?:;')
    
    if first_word == "YES":
        return True, first_word
    elif first_word == "NO":
        return False, first_word
    else:
        if VERBOSE:
            print(f"[WARN] Unexpected answer: '{first_word}' - treating as NOT RELEVANT")
        return False, first_word


def llm_filter(title: str, abstract: str) -> bool:
    if VERBOSE:
        print(f"[DEBUG] Filtering paper: '{title[:60]}...'")
        print(f"[DEBUG] Abstract length: {len(abstract)} characters")
    prompt = f"""You are filtering papers for relevance to COMPUTER SCIENCE topics about data management and processing.

The paper must be DIRECTLY and SUBSTANTIALLY related to one or more of these specific topics:
- Unstructured data analysis (methods for analyzing text, documents, or unstructured formats)
- Querying unstructured data (searching, querying, or retrieving information from unstructured sources)
- Semi-structured data analysis (working with JSON, XML, or other semi-structured formats)
- Text-to-table conversion (extracting structured tables from unstructured text)
- Text-to-relational schema (converting text into database schemas or relational models)

EXCLUDE papers that are:
- About physics, astronomy, biology, chemistry, or other natural sciences (even if they mention "data analysis")
- About general machine learning or AI without focus on data management/processing
- About databases or data systems without focus on unstructured/semi-structured data
- Only tangentially related (e.g., using data analysis as a tool but not about data management itself)

Title: {title}
Abstract: {abstract}

Is this paper DIRECTLY about computer science topics related to unstructured/semi-structured data management, querying, or conversion? 

Respond with ONLY one word: YES or NO. Do not explain."""
    if VERBOSE:
        print(f"[DEBUG] Calling Ollama with model: {MODEL}")
        print(f"[DEBUG] Prompt length: {len(prompt)} characters")
    start_time = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", MODEL],
            input=prompt.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        elapsed = time.time() - start_time
        
        stdout_text = result.stdout.decode('utf-8', errors='replace') if isinstance(result.stdout, bytes) else result.stdout
        output = stdout_text.strip()
        if VERBOSE:
            print(f"[DEBUG] LLM response received in {elapsed:.2f}s")
            if output:
                
                if len(output) <= 500:
                    print(f"[DEBUG] Raw LLM output (full): {output}")
                else:
                    print(f"[DEBUG] Raw LLM output (first 500 chars): {output[:500]}...")
                    print(f"[DEBUG] Raw LLM output (last 200 chars): ...{output[-200:]}")
                print(f"[DEBUG] Raw LLM output length: {len(output)} characters")
            else:
                print(f"[DEBUG] Raw LLM output: (EMPTY - no response received)")
        
        is_relevant, extracted_answer = parse_llm_response(output)
        if VERBOSE:
            print(f"[DEBUG] Extracted answer: '{extracted_answer}'")
            print(f"[DEBUG] Relevance decision: {'RELEVANT' if is_relevant else 'NOT RELEVANT'}")
        return is_relevant
    except Exception as e:
        print(f"[WARN] LLM filter failed: {e}")
        if VERBOSE:
            print(f"[DEBUG] Exception type: {type(e).__name__}")
            print(f"[DEBUG] Exception details: {str(e)}")
        return False


def format_entry(entry):
    """Return a formatted string for each arXiv entry."""
    return (
        f"Title: {entry.title.strip()}\n"
        f"Authors: {', '.join(a.name for a in entry.authors)}\n"
        f"Date: {entry.published}\n"
        f"Link: {entry.link}\n"
        f"Summary: {entry.summary.strip()[:600]}...\n"
        f"{'-'*80}\n"
    )


def send_batch_email_notification(papers_list):
    """Send a single email notification with all new relevant papers found."""
    if not papers_list:
        return False
        
    if not USER_EMAIL or not SMTP_USERNAME or not SMTP_PASSWORD:
        if VERBOSE:
            print(f"[WARN] Email configuration incomplete. Skipping email notification.")
            print(f"[DEBUG] USER_EMAIL: {'set' if USER_EMAIL else 'not set'}")
            print(f"[DEBUG] SMTP_USERNAME: {'set' if SMTP_USERNAME else 'not set'}")
            print(f"[DEBUG] SMTP_PASSWORD: {'set' if SMTP_PASSWORD else 'not set'}")
        return False
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = USER_EMAIL
        
        paper_count = len(papers_list)
        if paper_count == 1:
            msg['Subject'] = f"New Relevant arXiv Paper Found: {papers_list[0][0].title.strip()[:60]}"
        else:
            msg['Subject'] = f"New Relevant arXiv Papers Found: {paper_count} papers"
        
        # Create email body with all papers (only title, link, and date)
        body = f"""Found {paper_count} new relevant paper{'s' if paper_count > 1 else ''} on arXiv!

"""
        for entry, paper_id in papers_list:
            # Format date nicely
            published_date = datetime.strptime(
                entry.published, "%Y-%m-%dT%H:%M:%SZ"
            ).strftime("%Y-%m-%d")
            
            body += f"Title: {entry.title.strip()}\n"
            body += f"Date: {published_date}\n"
            body += f"Link: {entry.link}\n"
            body += f"{'-'*80}\n\n"
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        if VERBOSE:
            print(f"[DEBUG] Sending email notification to {USER_EMAIL}...")
        
        server = None
        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()  # Enable TLS encryption
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            text = msg.as_string()
            server.sendmail(SMTP_USERNAME, USER_EMAIL, text)
            
            if VERBOSE:
                print(f"[INFO] Email notification sent successfully to {USER_EMAIL}")
            return True
        finally:
            if server:
                try:
                    server.quit()
                except Exception as quit_error:
                    if VERBOSE:
                        print(f"[DEBUG] Error closing SMTP connection: {quit_error}")
        
    except Exception as e:
        print(f"[WARN] Failed to send email notification: {e}")
        if VERBOSE:
            print(f"[DEBUG] Exception details: {type(e).__name__}: {str(e)}")
        return False


def main():
    if VERBOSE:
        print("[DEBUG] Starting arXiv agent...")
        print(f"[DEBUG] Configuration:")
        print(f"  - Topics: {len(TOPICS)} topics")
        print(f"  - Max results per topic: {MAX_RESULTS}")
        print(f"  - Model: {MODEL}")
        print(f"  - Days back: {DAYS_BACK}")
        print(f"  - Verbose mode: {VERBOSE}")
    
    cached_paper_ids = load_relevant_paper_ids(RELEVANT_PAPERS_FILE)
    
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=DAYS_BACK)
    if VERBOSE:
        print(f"[DEBUG] Date range: {week_ago.date()} to {now.date()}")
        print(f"[DEBUG] Current UTC time: {now}")
    
    relevant_papers = []
    new_relevant_papers = []  
    total_entries_processed = 0
    total_entries_in_range = 0
    total_llm_calls = 0
    total_cached_hits = 0

    for idx, topic in enumerate(TOPICS, 1):
        if VERBOSE:
            print(f"\n[INFO] Processing topic {idx}/{len(TOPICS)}: '{topic}'")
        print(f"\n--- Searching for: {topic} ---\n")

        entries = query_arxiv(topic, MAX_RESULTS)
        total_entries_processed += len(entries)
        
        if VERBOSE:
            print(f"[DEBUG] Found {len(entries)} total entries for topic '{topic}'")

        topic_relevant_count = 0
        for entry_idx, entry in enumerate(entries, 1):
            if VERBOSE:
                print(f"[DEBUG] Processing entry {entry_idx}/{len(entries)} for topic '{topic}'")
            
            published_date = datetime.strptime(
                entry.published, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)

            if VERBOSE:
                print(f"[DEBUG] Entry published date: {published_date.date()}")

            # keep entries published in the last 7 days
            if not (week_ago <= published_date <= now):
                if VERBOSE:
                    print(f"[DEBUG] Entry outside date range, skipping")
                continue

            total_entries_in_range += 1
            if VERBOSE:
                print(f"[DEBUG] Entry within date range, checking relevance...")

            title = entry.title
            abstract = entry.summary
            
            # Extract paper ID
            paper_id = extract_paper_id(entry)
            if not paper_id:
                if VERBOSE:
                    print(f"[WARN] Could not extract paper ID for entry, skipping cache check")
                paper_id = None
            
            is_relevant = False
            if paper_id and paper_id in cached_paper_ids:
                is_relevant = True
                total_cached_hits += 1
                if VERBOSE:
                    print(f"[DEBUG] Paper ID '{paper_id}' found in cache, skipping LLM call")
            else:
                
                if VERBOSE:
                    if paper_id:
                        print(f"[DEBUG] Paper ID '{paper_id}' not in cache, checking with LLM...")
                    else:
                        print(f"[DEBUG] Paper ID unknown, checking with LLM...")
                
                total_llm_calls += 1
                is_relevant = llm_filter(title, abstract)
                
                if is_relevant:
                    is_new_paper = not paper_id or paper_id not in cached_paper_ids
                    
                    if paper_id:
                        cached_paper_ids.add(paper_id)
                        save_paper_id(RELEVANT_PAPERS_FILE, paper_id)
                        if VERBOSE:
                            print(f"[INFO] Added paper ID '{paper_id}' to cache")
                    
                    if is_new_paper:
                        new_relevant_papers.append((entry, paper_id))
                        if VERBOSE:
                            print(f"[INFO] New relevant paper found, queued for email notification")
            
            if is_relevant:
                topic_relevant_count += 1
                relevant_papers.append((published_date.date(), format_entry(entry)))
                if VERBOSE:
                    print(f"[INFO] Paper marked as RELEVANT: '{title[:60]}...'")
            else:
                if VERBOSE:
                    print(f"[INFO] Paper marked as NOT RELEVANT: '{title[:60]}...'")

        if VERBOSE:
            print(f"[INFO] Topic '{topic}' summary: {topic_relevant_count} relevant papers found")
        
        if idx < len(TOPICS):
            if VERBOSE:
                print(f"[DEBUG] Waiting 3 seconds before next topic (rate limiting)...")
            time.sleep(3)  # Respecting the arXiv API

    if new_relevant_papers:
        if VERBOSE:
            print(f"\n[INFO] Pipeline complete. Sending single email notification for {len(new_relevant_papers)} new relevant paper(s)...")
        send_batch_email_notification(new_relevant_papers)
    else:
        if VERBOSE:
            print(f"\n[INFO] Pipeline complete. No new relevant papers found, skipping email notification.")

    if VERBOSE:
        print(f"\n[DEBUG] Processing complete:")
        print(f"  - Total entries retrieved: {total_entries_processed}")
        print(f"  - Entries in date range: {total_entries_in_range}")
        print(f"  - Cache hits (skipped LLM): {total_cached_hits}")
        print(f"  - Total LLM calls made: {total_llm_calls}")
        print(f"  - Relevant papers found: {len(relevant_papers)}")



if __name__ == "__main__":
    main()