import base64
import requests
import os

def convert_multiple_to_base64(urls):
    combined_text = ""
    
    for url in urls:
        try:
            # Download text file from the URL
            response = requests.get(url, timeout=10) # Added timeout
            response.raise_for_status() # Raise an exception for HTTP errors
            # Try to decode with utf-8, fallback to other encodings if needed
            try:
                combined_text += response.content.decode('utf-8') + "\n"
            except UnicodeDecodeError:
                try:
                    combined_text += response.content.decode('gbk') + "\n" # Common Chinese encoding
                except UnicodeDecodeError:
                    combined_text += response.content.decode('latin-1', errors='ignore') + "\n" # Fallback, ignore errors
                    print(f"Warning: Could not decode content from {url} as UTF-8 or GBK. Used latin-1 with error handling.")
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch data from URL: {url} due to {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing URL {url}: {e}")


    # Remove duplicate lines while preserving order
    lines = combined_text.splitlines()
    unique_lines = []
    seen_lines = set() # Stores stripped lines to check for duplicates
    for line in lines:
        # Normalize line by stripping whitespace before checking for duplicates
        stripped_line = line.strip()
        # Add to unique_lines if the stripped line is not empty and not seen before
        if stripped_line and stripped_line not in seen_lines: 
            unique_lines.append(line) # Add original line (with its original spacing, but no trailing newline from splitlines)
            seen_lines.add(stripped_line) # Add the stripped version to the set of seen lines
    
    processed_text = "\n".join(unique_lines)
    # Add a final newline if there's content and it's not just whitespace
    if unique_lines and processed_text.strip(): 
        processed_text += "\n"


    # Encode processed text to base64
    encoded_bytes = base64.b64encode(processed_text.encode('utf-8'))
    encoded_text = encoded_bytes.decode('utf-8')

    # Check if content needs updating
    needs_update = True
    output_file = 'base64.txt'
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
                if encoded_text == existing_content:
                    needs_update = False
                    print("No changes detected. Content is up to date.")
                else:
                    print("Content has changed.")
        except Exception as e:
            print(f"Error reading existing file {output_file}: {e}. Assuming update is needed.")
            needs_update = True # Force update if reading fails

    # Save base64-encoded text (only if changed or file doesn't exist)
    if needs_update:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(encoded_text)
            print(f"Conversion complete and changes saved to {output_file}.")
        except Exception as e:
            print(f"Error writing to file {output_file}: {e}")

if __name__ == "__main__":
    urls = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/base.txt",
        "https://kurzlinks.de/13tc",
        # Add more URLs here if needed
    ]
    convert_multiple_to_base64(urls)
