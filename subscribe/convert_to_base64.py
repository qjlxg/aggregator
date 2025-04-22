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
        "https://raw.githubusercontent.com/qjlxg/py/refs/heads/main/sub/2504/250416.txt?token=GHSAT0AAAAAADBYZWPHR7DKQS3FFF6ZO2PKZ77PWDQ",
        "https://raw.githubusercontent.com/qjlxg/py/refs/heads/main/Long_term_subscription_num?token=GHSAT0AAAAAADBYZWPGX7GFVYGNRPYE4REGZ77O6IQ",
        "https://raw.githubusercontent.com/qjlxg/py/refs/heads/main/trial?token=GHSAT0AAAAAADBYZWPHC2SN4SXSMOAFGYUWZ77PCBQ"
    ]
    convert_multiple_to_base64(urls)
