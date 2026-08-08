import os
import datetime
import subprocess
import urllib.parse
import imaplib
import email
from email.header import decode_header
import signal
from google import genai
from google.genai import types

def get_system_time():
    """Returns the current date and time so Friday has a sense of time."""
    now = datetime.datetime.now()
    return f"The current date and time is: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"

def list_workspace_files(directory: str):
    """Allows Friday to see what files are in a folder. Always pass '.' to check the current folder."""
    try:
        files = os.listdir(directory)
        return f"Files in '{directory}': {', '.join(files)}"
    except Exception as e:
        return f"Error reading directory: {str(e)}"

def read_file_content(filepath: str):
    """Allows Friday to read the text inside a specific file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        return f"Content of {filepath}:\n{content}"
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file_content(filepath: str, content: str):
    """Allows Friday to write or overwrite a file with new code or text."""
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return f"Successfully wrote new content to {filepath}."
    except Exception as e:
        return f"Failed to write file: {str(e)}"

def read_latest_emails():
    """Fetches the 3 most recent emails from the user's Gmail inbox."""
    username = os.getenv("FRIDAY_EMAIL")
    password = os.getenv("FRIDAY_EMAIL_PASSWORD") 

    if not username or not password:
        return "Error: Tell the user to add FRIDAY_EMAIL and FRIDAY_EMAIL_PASSWORD to their .env file."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password)
        mail.select("inbox")

        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        latest_ids = email_ids[-3:] 
        
        email_summaries = []
        
        for e_id in latest_ids:
            res, msg = mail.fetch(e_id, "(RFC822)")
            for response in msg:
                if isinstance(response, tuple):
                    msg_obj = email.message_from_bytes(response[1])
                    
                    subject, encoding = decode_header(msg_obj["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                        
                    sender = msg_obj.get("From")
                    
                    body = ""
                    if msg_obj.is_multipart():
                        for part in msg_obj.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break 
                    else:
                        body = msg_obj.get_payload(decode=True).decode(errors="ignore")

                    body = body[:500] + "..." if len(body) > 500 else body
                    email_summaries.append(f"From: {sender}\nSubject: {subject}\nBody: {body}")

        mail.logout()
        
        if not email_summaries:
            return "The inbox is empty."
            
        return "Here are the latest 3 emails:\n\n" + "\n---\n".join(email_summaries)

    except imaplib.IMAP4.error:
        return "Authentication failed. Tell the user their App Password might be incorrect."
    except Exception as e:
        return f"Failed to access inbox: {str(e)}"

def draft_visual_email(to_email: str, subject: str, body: str):
    """Drafts an email and pops it open on the screen so the user can hit send."""
    subject_encoded = urllib.parse.quote(subject)
    body_encoded = urllib.parse.quote(body)
    
    if len(body_encoded) > 1500:
        return "Error: Draft is too long for a visual pop-up. Ask the user to shorten it."
    
    url = f"mailto:{to_email}?subject={subject_encoded}&body={body_encoded}"
    subprocess.run(["open", url])
    
    return f"Opened email draft to {to_email} on screen for confirmation."

def draft_calendar_event(title: str, description: str):
    """Opens a pre-filled Google Calendar event in the browser for the user to save."""
    title_encoded = urllib.parse.quote(title)
    desc_encoded = urllib.parse.quote(description)
    
    url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={title_encoded}&details={desc_encoded}"
    subprocess.run(["open", url])
    
    return "Opened Google Calendar event draft on screen for confirmation."

def shutdown_system():
    """Permanently kills the Friday background application (Hard Kill Switch)."""
    os.kill(os.getpid(), signal.SIGTERM)
    return "Shutting down immediately."

def analyze_screen():
    """Takes a silent screenshot of the Mac screen and tells Friday exactly what is visible safely."""
    try:
        subprocess.run(["screencapture", "-x", "temp_screen.jpg"])
        
        temp_client = genai.Client()
        default_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
        
        with open("temp_screen.jpg", "rb") as f:
            image_bytes = f.read()
            
        response = temp_client.models.generate_content(
            model=default_model,
            contents=[
                "You are the visual cortex of an AI. Analyze this screenshot and describe exactly what is on the screen in high detail. Mention any open apps, context, or code.",
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            ]
        )
        return f"SCREENSHOT ANALYSIS: {response.text}"
    except Exception as e:
        return f"Failed to analyze screen: {str(e)}"
    finally:
        if os.path.exists("temp_screen.jpg"):
            os.remove("temp_screen.jpg")