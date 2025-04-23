from openai import OpenAI
import requests
import time
from io import BytesIO
import os
import shutil
from flask import Flask, request, Response, session
from tempfile import NamedTemporaryFile
import traceback
from contextlib import contextmanager
import json
from datetime import datetime

# Initialize OpenAI client using environment variable from Render
api_key = os.getenv('Render')
if not api_key:
    raise ValueError("Render environment variable (OpenAI API key) is not set. Please check your Render environment configuration.")

client = OpenAI(api_key=api_key)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# Conversation storage configuration
CONVERSATION_STORAGE_DIR = "conversations"
os.makedirs(CONVERSATION_STORAGE_DIR, exist_ok=True)

# TTS Configuration
TTS_CONFIG = {
    "voice": "Polly.Joanna-Neural",
    "language": "en-US",
    "speech_rate": "medium",
    "pitch": "default",
    "volume": "default"
}

def save_conversation(call_sid, conversation_data):
    """Save conversation data to a file for future reference."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{CONVERSATION_STORAGE_DIR}/{call_sid}_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(conversation_data, f, indent=2)

def load_conversation(call_sid):
    """Load conversation data if it exists."""
    try:
        # Find the most recent conversation file for this call_sid
        files = [f for f in os.listdir(CONVERSATION_STORAGE_DIR) if f.startswith(call_sid)]
        if not files:
            return None
        latest_file = max(files)
        with open(os.path.join(CONVERSATION_STORAGE_DIR, latest_file), 'r') as f:
            return json.load(f)
    except Exception:
        return None

@contextmanager
def safe_temp_file(suffix=None):
    """Safely create and cleanup a temporary file."""
    temp_file = NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        yield temp_file
    finally:
        temp_file.close()
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

def extract_name_and_preference(transcript):
    """Extract name and preferred name from transcript with improved logic."""
    if not transcript:
        return "there", None
    
    # Clean and split the transcript
    words = transcript.strip().lower().split()
    if not words:
        return "there", None
    
    # Common introduction patterns with their variations
    intro_patterns = {
        "my name is": 3,
        "i'm": 1,
        "this is": 2,
        "i am": 2,
        "hello i'm": 2,
        "hi i'm": 2,
        "you can call me": 3,
        "please call me": 2,
        "everyone calls me": 2,
        "i go by": 2,
        "i prefer to be called": 3,
        "i like to be called": 3,
        "my friends call me": 3,
        "my nickname is": 2,
        "i'm known as": 2
    }
    
    # Check for introduction patterns
    transcript_lower = transcript.lower()
    for pattern, skip in intro_patterns.items():
        if pattern in transcript_lower:
            # Get the part after the pattern
            parts = transcript_lower.split(pattern, 1)
            if len(parts) > 1:
                name_parts = parts[1].strip().split()
                if name_parts:
                    # Check if there's a preferred name mentioned
                    preferred_name = None
                    if "but" in name_parts or "however" in name_parts:
                        for i, word in enumerate(name_parts):
                            if word in ["but", "however"] and i + 1 < len(name_parts):
                                preferred_name = name_parts[i + 1]
                                break
                    
                    return name_parts[0], preferred_name
    
    # If no pattern matches, take the first word as name
    return words[0], None

def generate_twiml_response(text, record_next=False, qid=0):
    """Generate TwiML response with enhanced TTS configuration"""
    say_attributes = f'voice="{TTS_CONFIG["voice"]}" language="{TTS_CONFIG["language"]}"'
    if TTS_CONFIG["speech_rate"] != "medium":
        say_attributes += f' rate="{TTS_CONFIG["speech_rate"]}"'
    if TTS_CONFIG["pitch"] != "default":
        say_attributes += f' pitch="{TTS_CONFIG["pitch"]}"'
    if TTS_CONFIG["volume"] != "default":
        say_attributes += f' volume="{TTS_CONFIG["volume"]}"'
    
    twiml = f'<Response><Say {say_attributes}>{text}</Say>'
    if record_next:
        twiml += f'<Record maxLength="10" action="/handle-response?q={qid}" method="POST" playBeep="false" />'
    twiml += '</Response>'
    return twiml

@app.route("/voice", methods=["POST"])
def voice():
    # Get call SID for conversation tracking
    call_sid = request.form.get('CallSid', 'unknown')
    
    # Initialize session data
    session['call_sid'] = call_sid
    session['conversation_log'] = []
    session['first_name'] = ""
    session['preferred_name'] = None
    session['conversation_complete'] = False
    
    # Try to load previous conversation if it exists
    previous_conversation = load_conversation(call_sid)
    if previous_conversation:
        session['conversation_log'] = previous_conversation.get('conversation_log', [])
        session['first_name'] = previous_conversation.get('first_name', "")
        session['preferred_name'] = previous_conversation.get('preferred_name')
    
    response = generate_twiml_response(
        "Hi! Thanks for calling. I'd like to get to know you better. Can I please have your full name?",
        record_next=True,
        qid=0
    )
    return Response(response, mimetype='text/xml')

@app.route("/handle-response", methods=["POST"])
def handle_response():
    call_sid = session.get('call_sid', 'unknown')
    
    if session.get('conversation_complete', False):
        return Response(
            generate_twiml_response("The call is complete. Thank you for your time."),
            mimetype='text/xml'
        )

    qid = int(request.args.get("q", 0))
    recording_url = request.form.get("RecordingUrl")
    
    if not recording_url:
        return Response(
            generate_twiml_response("I'm sorry, I didn't receive your response. Could you please try again?"),
            mimetype='text/xml'
        )
    
    recording_url += ".mp3"
    print("Recording URL:", recording_url)

    # Transcribe audio with improved error handling and longer delay
    max_retries = 3
    retry_delay = 5  # Increased initial delay
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Add delay before each attempt
            time.sleep(retry_delay)
            
            response = requests.get(recording_url, timeout=15)  # Increased timeout
            response.raise_for_status()
            
            with safe_temp_file(suffix=".mp3") as tmp:
                tmp.write(response.content)
                tmp.flush()
                
                with open(tmp.name, "rb") as audio_file:
                    resp = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                transcript = resp.text
                break
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                retry_delay *= 2  # Exponential backoff
                continue
            print("Error fetching recording:", e)
            return Response(
                generate_twiml_response("I'm having trouble hearing you. Could you please speak a bit louder and try again?"),
                mimetype='text/xml'
            )
        except Exception as e:
            traceback.print_exc()
            print("Error during transcription:", e)
            return Response(
                generate_twiml_response("I'm sorry, there was a technical issue understanding your answer. Let's try again."),
                mimetype='text/xml'
            )
    else:
        print("All retries failed:", last_error)
        return Response(
            generate_twiml_response("I'm having technical difficulties. Please try again in a moment."),
            mimetype='text/xml'
        )

    print("Transcript:", transcript)
    
    # Update session data
    conversation_log = session.get('conversation_log', [])
    
    if qid == 0:
        first_name, preferred_name = extract_name_and_preference(transcript)
        session['first_name'] = first_name
        if preferred_name:
            session['preferred_name'] = preferred_name
        conversation_log.append(f"Full name: {transcript}")
    else:
        first_name = session.get('preferred_name') or session.get('first_name', 'there')
        conversation_log.append(f"{first_name}: {transcript}")
    
    session['conversation_log'] = conversation_log
    
    # Save conversation state
    conversation_data = {
        'call_sid': call_sid,
        'conversation_log': conversation_log,
        'first_name': session.get('first_name'),
        'preferred_name': session.get('preferred_name'),
        'timestamp': datetime.now().isoformat()
    }
    save_conversation(call_sid, conversation_data)

    # Generate next question or closing with improved error handling
    try:
        system_prompt = (
            f"You are a friendly interviewer. Address the caller by their preferred name ({session.get('preferred_name')}) "
            f"if they have one, otherwise use their first name ({session.get('first_name')}). "
            "Ask one question at a time and never mention you're an AI. "
            "When done, say 'Thank you, that's all I need today.' and hang up."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(conversation_log)}
        ]
        chat = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        next_line = chat.choices[0].message.content.strip()
    except Exception as e:
        traceback.print_exc()
        print("Error during GPT analysis:", e)
        return Response(
            generate_twiml_response("I'm having trouble processing your response. Let's try again."),
            mimetype='text/xml'
        )

    print("Next Line:", next_line)
    
    if "thank you, that's all i need today" in next_line.lower():
        session['conversation_complete'] = True
        return Response(
            generate_twiml_response(next_line),
            mimetype='text/xml'
        )
    else:
        return Response(
            generate_twiml_response(next_line, record_next=True, qid=qid+1),
            mimetype='text/xml'
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
