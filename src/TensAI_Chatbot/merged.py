import os
import json
import datetime
import time
import random
import sqlite3
from datetime import timedelta
from flask import Flask, request, jsonify, render_template # type: ignore
from flask_cors import CORS # type: ignore
import requests # type: ignore
import fitz  # type: ignore # PyMuPDF
import boto3 # type: ignore
import uuid

# -------------------------------
# Flask Setup
# -------------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24) # "42c49afbd77de45bb67d01c4278a9b24"  # not strictly used now
CORS(app, supports_credentials=True)

# -------------------------------
# Database Setup
# -------------------------------
def init_db():
    conn = sqlite3.connect('user_conversations.db')
    c = conn.cursor()
    
    # Users table with pain_points column and expiry
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY,
                  username TEXT,
                  phone_number TEXT,
                  email TEXT,
                  pain_points TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  expires_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  username TEXT,
                  phone_number TEXT,
                  question TEXT,
                  answer TEXT,
                  pain_points TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    
    conn.commit()
    conn.close()

# -------------------------------
# Configuration / Secrets
# -------------------------------
def load_dict_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

secrets_file = "C:\\Users\\Anubhab Roy\\Downloads\\Nekko_WorkFiles\\Tensai Chat Prod\\chatbot\\secrets.json"
SECRETS = load_dict_from_json(secrets_file)

aws_access_key_id = SECRETS["aws_access_key_id"]
aws_secret_access_key = SECRETS["aws_secret_access_key"]
INFERENCE_PROFILE_ARN = SECRETS["INFERENCE_PROFILE_ARN"]
REGION = SECRETS["REGION"]

bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION,
                              aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key)

# -------------------------------
# (Optional) Document Analysis
# -------------------------------
def extract_text_from_pdf(uploaded_file):
    # uploaded_file should be a file-like object (e.g., BytesIO)
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    extracted_text = ""
    
    for page in pdf_document:
        extracted_text += page.get_text() + "\n"
    
    pdf_document.close()
    return extracted_text.strip()

with open("document.pdf", "rb") as f:
    company_info_text = extract_text_from_pdf(f)

# -------------------------------
# LLM Call Function
# -------------------------------
def call_llm_api(conversation_history):
    # Build the system message with your PDF content
    system_message = f"""
You are TensAI Chat, a helpful website chatbot for our company. Always follow these rules:

1. **Customer Info First**: 
   - Always greet the user and immediately ask for their **Name and Mobile Number** before answering any queries.
   - Politely explain that these are **required to assist them further**.
   - Optionally ask for **Email and Organisation** after Name & Mobile.

2. **Only Proceed After Details**: 
   - Do not provide product information or answer questions until Name & Mobile are received.
   - If user refuses, politely remind: "I need your Name and Mobile Number to assist you."

3. **Answering Queries**:
   - After collecting details, answer **briefly (≤50 words)** and stay relevant.
   - If query is unrelated, reply: "I am a helpful assistant, please ask me something else."
   - If user asks for sales contact, give **sangita@nekko.tech**.

4. **Formatting**:
   - Do not use markdown formatting.
   - Keep responses short, chat-friendly, and professional.

Company info and product details:
{company_info_text}
"""
    messages = [{"role": "system", "content": system_message}] + conversation_history

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(messages)
            }
        ]
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=INFERENCE_PROFILE_ARN,
                contentType='application/json',
                accept='application/json',
                body=json.dumps(payload)
            )
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
        except bedrock_runtime.exceptions.ThrottlingException:
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"Throttled. Retrying in {wait_time:.1f}s...")
            time.sleep(wait_time)
        except Exception as e:
            return f"An error occurred: {str(e)}"
    return "An error occurred: Max retries exceeded."

# --- LLM Call for Lead Extraction (with robust parsing) ---
def extract_lead_details_from_conversation(conversation):
    extraction_prompt = """
    You are tasked with extracting the following details from this conversation:
    - Name (if provided)
    - Phone Number
    - Email
    - Any pain points or comments shared by the user

    Return ONLY the information as a JSON object in this format:
    {
        "name": "",
        "phone": "",
        "email": "",
        "pain_points": ""
    }
    """

    user_query = f"The Conversation so far: {json.dumps(conversation)}"

    answer = call_llm_api([
        {"role": "system", "content": extraction_prompt}, 
        {"role": "user", "content": user_query}
    ])

    print("LLM response:\n", answer)

    # If the answer is not valid JSON, return empty fields
    if not answer or not answer.strip().startswith("{"):
        try:
            # Attempt to extract JSON from code block
            if "```json" in answer:
                answer = answer.split("```json")[1].split("```")[0].strip()
            elif "```" in answer:
                answer = answer.split("```")[1].split("```")[0].strip()
        except Exception:
            return {"name": "", "phone": "", "email": "", "pain_points": ""}

    try:
        return json.loads(answer)
    except Exception:
        return {"name": "", "phone": "", "email": "", "pain_points": ""}

# -------------------------------
# User Session Management (24h expiry)
# -------------------------------
def is_session_valid(user_id):
    """Check if the given session ID exists and is still valid."""
    conn = sqlite3.connect('user_conversations.db')
    c = conn.cursor()
    c.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return False

    expiry = datetime.datetime.fromisoformat(row[0])
    return datetime.datetime.now() < expiry
    
def get_or_create_user_id(session_id=None, user_info=None):
    """Get a valid session_id or create a new one if expired/nonexistent."""
    if session_id and is_session_valid(session_id):
        # Update user info if provided
        if user_info:
            update_user_info(session_id, 
                             username=user_info.get("name") or None,
                             phone_number=user_info.get("phone") or None,
                             email=user_info.get("email") or None,
                             pain_points=user_info.get("pain_points") or None)
        return session_id
    else:
        # Create a new session with 24h expiry
        new_session_id = str(uuid.uuid4())
        expiry_time = datetime.datetime.now() + datetime.timedelta(hours=24)

        conn = sqlite3.connect('user_conversations.db')
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (user_id, username, phone_number, email, pain_points, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            new_session_id,
            user_info.get("name") if user_info else None,
            user_info.get("phone") if user_info else None,
            user_info.get("email") if user_info else None,
            user_info.get("pain_points") if user_info else None,
            expiry_time.isoformat()
        ))
        conn.commit()
        conn.close()
        return new_session_id

def update_user_info(user_id, username=None, phone_number=None, email=None, pain_points=None):
    conn = sqlite3.connect('user_conversations.db')
    c = conn.cursor()

    update_fields = []
    params = []

    if username:
        update_fields.append("username = ?")
        params.append(username)
    if phone_number:
        update_fields.append("phone_number = ?")
        params.append(phone_number)
    if email:
        update_fields.append("email = ?")
        params.append(email)
    if pain_points:
        update_fields.append("pain_points = ?")
        params.append(pain_points)

    if update_fields:
        query = "UPDATE users SET " + ", ".join(update_fields) + " WHERE user_id = ?"
        params.append(user_id)
        c.execute(query, params)
        conn.commit()

    conn.close()

def save_conversation(user_id, question, answer):
    conn = sqlite3.connect('user_conversations.db')
    c = conn.cursor()
    c.execute("INSERT INTO conversations (user_id, question, answer) VALUES (?, ?, ?)",
              (user_id, question, answer))
    conn.commit()
    conn.close()

# -------------------------------
# Conversations and Contacts Folders
# -------------------------------
CONVERSATIONS_FOLDER = "conversations"
CONTACTS_FOLDER = "contacts"

if not os.path.exists(CONVERSATIONS_FOLDER):
    os.makedirs(CONVERSATIONS_FOLDER)
if not os.path.exists(CONTACTS_FOLDER):
    os.makedirs(CONTACTS_FOLDER)

# ---------------------------------------------------------
# Helper: Find newest JSON file in last 24 hours
# ---------------------------------------------------------
def latest_file_in_last_24h(folder, cutoff):
    """
    Return the path of the single newest .json file if its
    within the last 24 hours; else None.
    """
    newest_path = None
    newest_ctime = None
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            file_path = os.path.join(folder, filename)
            ctime = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
            # If file was created after cutoff, consider it
            if ctime >= cutoff:
                # Keep track of whichever is newest
                if newest_ctime is None or ctime > newest_ctime:
                    newest_ctime = ctime
                    newest_path = file_path
    return newest_path

# -------------------------------
# Routes
# -------------------------------
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_query = data.get("user_query", "").strip()
    session_id = data.get("session_id", str(uuid.uuid4()))

    if not user_query:
        return jsonify({"error": "No user query provided"}), 400

    # Load conversation history
    now = datetime.datetime.now()
    twenty_four_hours_ago = now - datetime.timedelta(hours=24)
    latest_path = latest_file_in_last_24h(CONVERSATIONS_FOLDER, twenty_four_hours_ago)
    if latest_path is not None:
        with open(latest_path, "r", encoding="utf-8") as f:
            combined_history = json.load(f)
    else:
        combined_history = []

    combined_history.append({"role": "user", "content": user_query})

    # Call LLM
    try:
        reply = call_llm_api(combined_history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    combined_history.append({"role": "assistant", "content": reply})

    # Extract user info *before* saving conversation
    user_info = extract_lead_details_from_conversation(combined_history)

    # Create or update user in DB
    user_id = get_or_create_user_id(session_id, user_info)

    # Save conversation
    save_conversation(user_id, user_query, reply)

    # Save conversation file
    if not latest_path:
        latest_path = os.path.join(
            CONVERSATIONS_FOLDER,
            f"chat_{now.strftime('%Y%m%d_%H%M%S')}.json"
        )
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(combined_history, f, indent=4)

    return jsonify({
        "reply": reply,
        "session_id": user_id
    })

# -------------------------------
# Lead Extraction Background Process
# -------------------------------
def lead_extraction_process():
    processed_files = {}  # key: filename, value: last processed modification timestamp

    while True:
        files = os.listdir(CONVERSATIONS_FOLDER)
        for file in files:
            if file.endswith(".json"):
                filepath = os.path.join(CONVERSATIONS_FOLDER, file)
                try:
                    # Get the file's current modification time
                    mod_time = os.path.getmtime(filepath)
                    
                    # Check if this file has not been processed or has been updated
                    if file not in processed_files or mod_time > processed_files[file]:
                        with open(filepath, "r", encoding="utf-8") as f:
                            conversation = json.load(f)
                        
                        # Extract lead details using the LLM
                        lead_data = extract_lead_details_from_conversation(conversation)
                        lead = lead_data
                        
                        if lead.get("name") and lead.get("phone"):
                            contact_file = os.path.join(CONTACTS_FOLDER, f"lead_{file}")
                            with open(contact_file, "w", encoding="utf-8") as cf:
                                json.dump(lead, cf, indent=4)
                            print(f"[{datetime.datetime.now()}] Extracted and saved lead from {file} to {contact_file}")
                        else:
                            print(f"[{datetime.datetime.now()}] Lead details not complete in {file}.")
                        
                        # Update processed_files with current modification time
                        processed_files[file] = mod_time
                except Exception as e:
                    print(f"Error processing {file}: {e}")
        # Wait before checking again (e.g., 10 seconds)
        time.sleep(10)

@app.route('/')
def index():
    return render_template('modified_ui.html')

# -------------------------------
# Main
# -------------------------------
if __name__ == '__main__':
    # Initialize the database tables if they don't exist
    init_db()

    # Start the lead extraction process in a separate thread
    import threading
    lead_thread = threading.Thread(target=lead_extraction_process, daemon=True)
    lead_thread.start()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)
