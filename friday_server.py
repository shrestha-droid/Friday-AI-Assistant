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

import logging
import uuid
import time
import asyncio
from datetime import datetime
from fastapi import Request, status
from fastapi.responses import JSONResponse

# ==========================================
# 1. INITIALIZE API & ENVIRONMENT & LOGGING
# ==========================================
load_dotenv()

LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] [%(request_id)s] %(message)s",
    handlers=[
        logging.FileHandler("friday.log"),
        logging.StreamHandler()
    ]
)

class RequestIDFilter(logging.Filter):
    def __init__(self, request_id="SYSTEM"):
        super().__init__()
        self.request_id = request_id
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = self.request_id
        return True

logger = logging.getLogger("friday")
logger.addFilter(RequestIDFilter())

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    logger.critical("Startup failed: GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required.")
    raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required.")

try:
    client = genai.Client(api_key=API_KEY)
except Exception as e:
    logger.critical(f"Failed to initialize Gemini client: {str(e)}")
    raise RuntimeError(f"Failed to initialize Gemini client: {str(e)}")

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"]
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "3000"))
ENABLE_HTTPS = os.getenv("ENABLE_HTTPS", "true").lower() == "true"
SSL_CERTFILE = os.getenv("SSL_CERTFILE", "")
SSL_KEYFILE = os.getenv("SSL_KEYFILE", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", f"https://localhost:{PORT},http://localhost:{PORT},https://127.0.0.1:{PORT},http://127.0.0.1:{PORT}").split(",") if o.strip()]
SESSION_TOKEN = os.getenv("FRIDAY_SESSION_TOKEN", "")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start_time = time.time()
    
    # Attach request_id to logging context
    old_factory = logging.getLogRecordFactory()
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = request_id
        return record
    logging.setLogRecordFactory(record_factory)

    path = request.url.path
    if path not in ["/health", "/api/health"]:
        logger.info(f"Incoming {request.method} {path}")
    
    try:
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000
        if path not in ["/health", "/api/health"]:
            logger.info(f"Completed {request.method} {path} status={response.status_code} duration={duration:.2f}ms")
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(f"Failed {request.method} {path} error={str(e)} duration={duration:.2f}ms")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal error occurred.", "request_id": request_id}
        )
    finally:
        logging.setLogRecordFactory(old_factory)

class CommandRequest(BaseModel):
    text: str
    model: str = DEFAULT_MODEL
    session_token: str | None = None

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

command_lock = asyncio.Lock()

# ==========================================
# 4. THE API ENDPOINTS
# ==========================================
@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Returns backend status, version, and Gemini client configuration state."""
    gemini_configured = False
    try:
        if client:
            gemini_configured = True
    except Exception:
        pass
    return {
        "status": "online",
        "version": "1.0.0",
        "gemini_configured": gemini_configured,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
async def serve_ui():
    """Serves the index.html file"""
    return FileResponse("index.html")

@app.get("/api/models")
async def list_models():
    """Returns a list of accessible Gemini models based on the API key"""
    try:
        models = []
        for m in client.models.list():
            if hasattr(m, 'supported_generation_methods') and 'generateContent' in m.supported_generation_methods:
                model_name = m.name.replace('models/', '')
                models.append(model_name)
            elif hasattr(m, 'name'):
                model_name = m.name.replace('models/', '')
                if 'gemini' in model_name:
                    models.append(model_name)
        if not models:
            models = [DEFAULT_MODEL] + FALLBACK_MODELS
        return {"models": sorted(list(set(models)))}
    except Exception as e:
        logger.error(f"Model List Error: {str(e)}")
        return {"models": sorted(list(set([DEFAULT_MODEL] + FALLBACK_MODELS)))}

@app.post("/api/command")
async def handle_command(request: CommandRequest):
    if SESSION_TOKEN and request.session_token != SESSION_TOKEN:
        logger.warning("Unauthorized API request attempt with invalid/missing session token.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.")

    user_text = request.text.strip()
    if not user_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Command text cannot be empty.")
    if len(user_text) > 4000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Command text exceeds maximum allowed length of 4000 characters.")

    requested_model = request.model if request.model else DEFAULT_MODEL
    logger.info(f"Processing command (Model: {requested_model}) length={len(user_text)}")
    
    async with command_lock:
        try:
            active_chat = client.chats.create(model=requested_model, config=config)
            
            def run_gemini():
                return active_chat.send_message(user_text)

            try:
                response = await asyncio.wait_for(asyncio.to_thread(run_gemini), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("Gemini API call timed out.")
                raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="The AI service request timed out.")

            tool_iterations = 0
            while response.function_calls and tool_iterations < 10:
                tool_iterations += 1
                function_responses = []
                for fn in response.function_calls:
                    logger.info(f"Executing tool: {fn.name}")
                    if fn.name in tool_execution_map:
                        try:
                            result = tool_execution_map[fn.name](**fn.args) if fn.args else tool_execution_map[fn.name]()
                        except Exception as tool_err:
                            logger.error(f"Tool execution error in {fn.name}: {str(tool_err)}")
                            result = f"Error executing tool {fn.name}: internal error."
                    else:
                        logger.warning(f"Requested unauthorized or missing tool: {fn.name}")
                        result = f"Error: Tool {fn.name} is not armed."
                        
                    function_responses.append(
                        types.Part.from_function_response(
                            name=fn.name,
                            response={"result": str(result)}
                        )
                    )
                
                def run_gemini_tools():
                    return active_chat.send_message(function_responses)

                try:
                    response = await asyncio.wait_for(asyncio.to_thread(run_gemini_tools), timeout=30.0)
                except asyncio.TimeoutError:
                    logger.error("Gemini API tool-response call timed out.")
                    raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="The AI service request timed out during tool execution.")
                
            ai_reply = response.text if response.text else "Operation completed."
            logger.info("Command completed successfully.")
            return {"response": ai_reply}
            
        except HTTPException as he:
            raise he
        except Exception as e:
            err_str = str(e).lower()
            logger.error(f"Gemini API error: {str(e)}")
            if "api key" in err_str or "auth" in err_str or "credential" in err_str:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Gemini authentication failure. Verify API credentials.")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The AI service request failed.")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"========================================")
    logger.info(f" FRIDAY BRAIN ONLINE ({HOST}:{PORT}, HTTPS={ENABLE_HTTPS})")
    logger.info(f"========================================")
    
    server_kwargs = {
        "host": HOST,
        "port": PORT,
        "log_level": "info"
    }
    
    if ENABLE_HTTPS:
        if SSL_CERTFILE and SSL_KEYFILE and os.path.exists(SSL_CERTFILE) and os.path.exists(SSL_KEYFILE):
            server_kwargs["ssl_certfile"] = SSL_CERTFILE
            server_kwargs["ssl_keyfile"] = SSL_KEYFILE
        else:
            # Generate a temporary dev self-signed cert or use standard fallback paths if available
            cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
            os.makedirs(cert_dir, exist_ok=True)
            cert_path = os.path.join(cert_dir, "cert.pem")
            key_path = os.path.join(cert_dir, "key.pem")
            if not (os.path.exists(cert_path) and os.path.exists(key_path)):
                try:
                    subprocess.run([
                        "openssl", "req", "-x509", "-newkey", "rsa:2048",
                        "-keyout", key_path, "-out", cert_path, "-days", "365",
                        "-nodes", "-subj", "/CN=localhost"
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            if os.path.exists(cert_path) and os.path.exists(key_path):
                server_kwargs["ssl_certfile"] = cert_path
                server_kwargs["ssl_keyfile"] = key_path

    uvicorn.run(app, **server_kwargs)