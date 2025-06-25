import os
from notion_client import Client
from typing import List, Optional, Dict, Any, Tuple
import requests
import sys
import time
import fitz
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from notion_client import Client as NotionClient
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ========== LOGGING SETUP ==========
now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"logs/log_{now}.log"
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()


# Initialize Notion client
NOTION_TOKEN = os.getenv("NOTION_TOKEN") 
notion = Client(auth=NOTION_TOKEN)

CLIENT_ID = os.getenv("CLIENT_ID") 
CLIENT_SECRET = os.getenv("CLIENT_SECRET") 

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate_google_drive():
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=SCOPES
    )
    creds = flow.run_local_server(port=0)
    service = build('drive', 'v3', credentials=creds)
    return service

def get_all_pages(database_id: str) -> List[Dict[str, Any]]:
    """Retrieve all pages in the database (with pagination)."""
    all_pages = []
    cursor = None

    try:
        while True:
            response = notion.databases.query(
                database_id=database_id,
                start_cursor=cursor
            )
            all_pages.extend(response["results"])
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return all_pages
    except Exception as e:
        log.error(f"❌ Failed to query database: {e}")
        return []


def get_property_value(page: Dict[str, Any], column_name: str) -> Optional[str]:
    """Extracts the value of a given property (column) from a page."""
    try:
        prop = page["properties"].get(column_name)
        if not prop:
            return None

        prop_type = prop["type"]
        value = prop.get(prop_type)

        if value is None:
            return None

        # Handle different property types
        if prop_type == "title":
            return value[0]["text"]["content"] if value else ""
        elif prop_type == "rich_text":
            return value[0]["text"]["content"] if value else ""
        elif prop_type == "select":
            return value.get("name", "")
        elif prop_type == "multi_select":
            return ", ".join([v["name"] for v in value])
        elif prop_type == "number":
            return str(value)
        elif prop_type == "checkbox":
            return str(value)
        elif prop_type == "date":
            return value.get("start")
        elif prop_type == "people":
            return ", ".join([p.get("name", "Unknown") for p in value])
        elif prop_type == "files":
            # Return comma-separated URLs or names
            files_info = []
            for file in value:
                if file["type"] == "external":
                    files_info.append(file["external"]["url"])
                elif file["type"] == "file":
                    files_info.append(file["file"]["url"])
            return ", ".join(files_info)
        else:
            return f"(Unhandled type: {prop_type})"
    except Exception as e:
        log.error(f"⚠️ Error reading property '{column_name}': {e}")
        return None

def download_file(url: str, output_dir="downloads") -> Optional[Tuple[str, str]]:
    os.makedirs(output_dir, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0]
    filepath = os.path.join(output_dir, filename)

    try:
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Downloaded: {filename}")
        return filepath, filename
    except Exception as e:
        log.error(f"❌ Failed to download {url}: {e}")
        return None


def extract_text_to_single_file(pdf_path, output_file):
    try:
        log.info(f"Opening PDF for extraction: {pdf_path}")
        doc = fitz.open(pdf_path)

        text = ""
        with open(output_file, "w", encoding="utf-8") as f_out:
            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]
                    text = page.get_text()
                    f_out.write(text)
                except Exception as e:
                    log.error(f"Failed to extract page {page_num + 1}: {e}")
        return text
        
    except Exception as e:
        log.error(f"Failed to process PDF: {e}")

def txt_to_json(txt_path: str, name: str, json_path: str = "output.json") -> None:
    """
    Reads a text file and writes its content to a JSON file with the structure:
    {
        "name": <name>,
        "content": <text content>
    }

    Args:
        txt_path (str): Path to the input .txt file.
        name (str): Name to use as the 'name' field in the JSON.
        json_path (str): Path to the output .json file (default is 'output.json').
    """
    try:
        with open(txt_path, "r", encoding="utf-8") as file:
            content = file.read()

        data = {
            "name": name,
            "content": content
        }

        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=2)

    except FileNotFoundError:
        log.error(f"❌ Error: The file '{txt_path}' does not exist.")
    except Exception as e:
        log.error(f"❌ Unexpected error: {e}")

def ensure_property_exists(notion, database_id, property_name, property_type):
    # Get current database schema
    db = notion.databases.retrieve(database_id=database_id)
    
    # Check if property already exists
    if property_name in db["properties"]:
        return

    # Add new property
    notion.databases.update(
        database_id=database_id,
        properties={
            property_name: {
                property_type: {}
            }
        }
    )
    log.info(f"Added new property '{property_name}' of type '{property_type}'.")


def split_text_file_into_chunks(file_path, chunk_size=1900):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
            return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    except FileNotFoundError:
        log.error(f"❌ File not found: {file_path}")
        return []
    except Exception as e:
        log.error(f"❌ Error reading file: {e}")
        return []

def upload_file_to_drive(service, file_path, file_name):
    file_metadata = {'name': file_name}
    media = MediaFileUpload(file_path, mimetype='text/plain')

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    file_id = file.get('id')

    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()

    shareable_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return shareable_link

def update_notion_file_column(notion, page_id, file_url, file_name, file_column="JSON Files"):
    """
    Update a Notion page with a file link in a Files column.

    :param notion_token: Notion integration token
    :param page_id: The ID of the Notion page to update
    :param file_url: The shareable file URL (e.g., from Google Drive)
    :param file_name: The name of the file (e.g., 'uploaded_text.txt')
    :param file_column: The name of the Notion column (default is 'File')
    """

    response = notion.pages.update(
        page_id=page_id,
        properties={
            file_column: {
                "files": [
                    {
                        "name": file_name,
                        "external": {
                            "url": file_url
                        }
                    }
                ]
            }
        }
    )
    log.info(f"✅ Updated Notion page: {response['id']}")

def remove_file_from_folder(file_path):
    """
    Deletes a file from a folder.

    :param folder_path: The path to the folder
    :param file_name: The name of the file to delete
    """
    
    if os.path.isfile(file_path):
        os.remove(file_path)
    else:
        log.error(f"File not found: {file_path}")

def file_exists(file_path):
    return os.path.exists(file_path)

def main():

    # auth google drive first
    service = authenticate_google_drive()

    DATABASE_ID = "47e4fd5e-879c-4fe4-bcf4-55a6879199f2"
    TARGET_COLUMN = "Files & media"
    JSON_FILES_COLUMN = "JSON Files"

    pages = get_all_pages(DATABASE_ID)
    log.info(f"📄 Found {len(pages)} pages.")

    for i, page in enumerate(pages, 1):
        value = get_property_value(page, TARGET_COLUMN)
        page_id = page['id']

        # Download files if present
        if value:
            pdf_path = ""
            txt_output_dir = "output_txt"
            json_output_dir = "output_json"
            pdf_output_dir = "downloads"

            os.makedirs(txt_output_dir, exist_ok=True)
            os.makedirs(json_output_dir, exist_ok=True)
            
            log.info("Downloading PDF...")

            pdf_path, filename = download_file(value)
            time.sleep(1)
            #pdf_path = "downloads\REFASHIOND_2024_State_of_Supply_Chain.pdf"

            if pdf_path:

                
                filepath = os.path.join(txt_output_dir, filename[:-4] + ".txt")  
                json_filepath = os.path.join(json_output_dir, filename[:-4] + ".json")

                extract_text_to_single_file(pdf_path = pdf_path, output_file=filepath)

                txt_to_json(txt_path=filepath, name=filename, json_path=json_filepath)


                json_filename = ""
                if filename.endswith(".pdf"):
                    new_filename = filename[:-4] + ".txt"  # Remove last 4 chars
                    json_filename = filename[:-4] + ".json"
                else:
                    new_filename = filename

                txt_filepath = os.path.join(txt_output_dir, new_filename)
                json_filepath = os.path.join(json_output_dir, json_filename) 
                pdf_filepath = os.path.join(pdf_output_dir, filename)  
                # Upload to google drive and get the public link
                log.info("Uploading to Google Drive...")
                shareable_link = upload_file_to_drive(service, json_filepath, json_filename)
                log.info(f"✅ Google Drive link: {shareable_link}")

                # Ensure the property exists before updating
                ensure_property_exists(
                    notion=notion,
                    database_id=DATABASE_ID,
                    property_name=JSON_FILES_COLUMN,
                    property_type="files"
                )

                # Update JSON Files column in Notion with the generated google drive link
                update_notion_file_column(notion, page_id, shareable_link, filename, file_column=JSON_FILES_COLUMN)

                # Delete the file
                remove_file_from_folder(pdf_filepath)
                remove_file_from_folder(json_filepath)
                remove_file_from_folder(txt_filepath)

if __name__ == "__main__":
    log.info("✅ Application has started. Do not interrupt.")
    main()
    log.info("✅ All operations completed.")
  