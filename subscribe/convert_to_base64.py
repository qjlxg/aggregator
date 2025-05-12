#https://github.com/VPNforWindowsSub/base64
import base64
import requests
import os

def convert_multiple_to_base64(urls):
    combined_text = ""
    
    for url in urls:
        # Download text file from the URL
        response = requests.get(url)
        if response.status_code == 200:
            combined_text += response.text + "\n"  
        else:
            print(f"Failed to fetch data from URL: {url}")

    # Encode combined text to base64
    encoded_bytes = base64.b64encode(combined_text.encode('utf-8'))
    encoded_text = encoded_bytes.decode('utf-8')

    # Check if content needs updating
    needs_update = True
    if os.path.exists('base64.txt'):
        with open('base64.txt', 'r') as f:
            existing_content = f.read()
            if encoded_text == existing_content:
                needs_update = False

    # Save base64-encoded text (only if changed)
    if needs_update:
        with open('base64.txt', 'w') as f:
            f.write(encoded_text)
        print("Conversion complete and changes saved.")
    else:
        print("No changes detected.")

if __name__ == "__main__":
    urls = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/base.txt",
    
        
    ]
    convert_multiple_to_base64(urls)
