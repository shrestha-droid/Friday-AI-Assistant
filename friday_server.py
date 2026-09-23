import os
import json
import subprocess
import psutil
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

import tools 

# ==========================================
# 1. INITIALIZE API & ENVIRONMENT
# ==========================================
load_dotenv()
client = genai.Client()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandRequest(BaseModel):
    text: str

# ==========================================
# 2. MEMORY & SYSTEM TOOLS
# ==========================================
MEMORY_FILE = "friday_memory.json"

def load_memory_db():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_memory_db(data):
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def store_memory(topic: str, content: str):
    db = load_memory_db()
    if topic in db:
        db[topic] = db[topic] + " | " + content
    else:
        db[topic] = content
    save_memory_db(db)
    return f"Successfully stored memory for topic: '{topic}'"

def query_memory(query: str):
    db = load_memory_db()
    query_lower = query.lower()
    for topic, content in db.items():
        if query_lower in topic.lower() or query_lower in content.lower():
            return f"Memory retrieved -> {topic}: {content}"
    return "No relevant information found in memory."

def get_system_stats():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    return f"MacBook Status -> CPU: {cpu}% | RAM: {ram}% | Disk: {disk}%"

def open_application(app_name: str):
    try:
        subprocess.run(["open", "-a", app_name], check=True)
        return f"Successfully launched {app_name}."
    except Exception as e:
        return f"Failed to launch {app_name}: {str(e)}"

def execute_terminal_command(command: str):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout if result.stdout else result.stderr
        return output if output else "Command executed with no output."
    except Exception as e:
        return f"Execution error: {str(e)}"

def enter_standby():
    return "Going to sleep."

# ==========================================
# 3. CORE AI SETUP
# ==========================================
try:
    with open("system_prompt.txt", "r") as file:
        FRIDAY_SYSTEM_INSTRUCTION = file.read()
except FileNotFoundError:
    FRIDAY_SYSTEM_INSTRUCTION = "You are Friday, an AI assistant."

EMOTION_DIRECTIVE = """
CRITICAL DIRECTIVE: Keep your responses incredibly brief. 1 to 2 short sentences maximum. 
You are communicating via a fast text-to-speech engine in a browser. Be conversational.
"""
FRIDAY_SYSTEM_INSTRUCTION += EMOTION_DIRECTIVE

tools_list = [
    tools.get_system_time, tools.list_workspace_files, tools.read_file_content,
    get_system_stats, open_application, execute_terminal_command, store_memory, query_memory, enter_standby
]

for tool_name in ["write_file_content", "read_latest_emails", "draft_visual_email", "draft_calendar_event", "shutdown_system", "analyze_screen"]:
    if hasattr(tools, tool_name):
        tools_list.append(getattr(tools, tool_name))

tool_execution_map = {t.__name__: t for t in tools_list}

config = types.GenerateContentConfig(
    system_instruction=FRIDAY_SYSTEM_INSTRUCTION,
    tools=tools_list,
    temperature=0.4 
)

chat = client.chats.create(model=DEFAULT_MODEL, config=config)

# ==========================================
# 4. THE API ENDPOINTS
# ==========================================
@app.get("/")
async def serve_ui():
    """Serves the index.html file when you visit localhost:8000"""
    return FileResponse("index.html")

@app.post("/api/command")
async def handle_command(request: CommandRequest):
    user_text = request.text
    print(f"\n[User Input]: {user_text}")
    
    try:
        response = chat.send_message(user_text)
        
        while response.function_calls:
            function_responses = []
            for fn in response.function_calls:
                print(f"[⚡ Friday Executing Tool: {fn.name}...]")
                if fn.name in tool_execution_map:
                    try:
                        result = tool_execution_map[fn.name](**fn.args) if fn.args else tool_execution_map[fn.name]()
                    except Exception as tool_err:
                        result = f"Error executing tool {fn.name}: {str(tool_err)}"
                else:
                    result = f"Error: Tool {fn.name} is not armed."
                    
                # Format response correctly for google-genai SDK
                function_responses.append(
                    types.Part.from_function_response(
                        name=fn.name,
                        response={"result": str(result)}
                    )
                )
                
            response = chat.send_message(function_responses)
            
        ai_reply = response.text if response.text else "Operation completed."
        print(f"[Friday AI]: {ai_reply}")
        return {"response": ai_reply}
        
    except Exception as e:
        print(f"[System Error]: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail="The AI service is unavailable. Check the Gemini API credentials."
        ) from e

if __name__ == "__main__":
    import uvicorn
    print("========================================")
    print(" FRIDAY BRAIN ONLINE (PORT 8000)")
    print("========================================")
    uvicorn.run(app, host="0.0.0.0", port=8000)