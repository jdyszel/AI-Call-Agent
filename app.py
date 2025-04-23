from openai import OpenAI
import requests
import time
from io import BytesIO
import os
from flask import Flask, request, Response
from tempfile import NamedTemporaryFile
import traceback

# Initialize OpenAI client using environment variable OPENAI_API_KEY
client = OpenAI()
app = Flask(__name__)

# In-memory conversation state
conversation_log = []
first_name = ""
conversation_complete = False

# TTS Configuration
TTS_CONFIG = {
    "voice": "Polly.Joanna-Neural",  # Using neural voice for more natural sound
    "language": "en-US",
    "speech_rate": "medium",  # Can be 'slow', 'medium', or 'fast'
    "pitch": "default",  # Can be 'x-low', 'low', 'default', 'high', 'x-high'
    "volume": "default"  # Can be 'silent', 'x-soft', 'soft', 'medium', 'loud', 'x-loud'
}

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
    # Start conversation by asking for full name
    conversation_log.clear()
    response = generate_twiml_response(
        "Hi! Thanks for calling. I'd like to get to know you better. Can I please have your full name?",
        record_next=True,
        qid=0
    )
    return Response(response, mimetype='text/xml')

@app.route("/handle-response", methods=["POST"])
def handle_response():
    global conversation_log, first_name, conversation_complete

    if conversation_complete:
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

    # Add a small delay to ensure the recording is available
    time.sleep(2)

    # Transcribe audio with improved error handling
    try:
        response = requests.get(recording_url, timeout=10)
        response.raise_for_status()
        audio_data = response.content
        
        with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_data)
            tmp.flush()
            
        with open(tmp.name, "rb") as audio_file:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        transcript = resp.text
    except requests.exceptions.RequestException as e:
        print("Error fetching recording:", e)
        return Response(
            generate_twiml_response("I'm having trouble hearing you. Could you please speak a bit louder?"),
            mimetype='text/xml'
        )
    except Exception as e:
        traceback.print_exc()
        print("Error during transcription:", e)
        return Response(
            generate_twiml_response("I'm sorry, there was a technical issue understanding your answer. Let's try again."),
            mimetype='text/xml'
        )

    print("Transcript:", transcript)
    # Save transcript and extract first name
    if qid == 0:
        parts = transcript.strip().split()
        first_name = parts[1] if parts and parts[0].lower() in ["my","i'm","i"] and len(parts) > 1 else (parts[0] if parts else "there")
        conversation_log.append(f"Full name: {transcript}")
    else:
        conversation_log.append(f"{first_name}: {transcript}")

    # Generate next question or closing with improved error handling
    try:
        system_prompt = (
            f"You are a friendly interviewer. Address the caller by their first name, {first_name}."
            " Ask one question at a time and never mention you're an AI."
            " When done, say 'Thank you, that's all I need today.' and hang up."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(conversation_log)}
        ]
        chat = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7  # Add some variability to responses
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
        conversation_complete = True
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
