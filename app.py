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

@app.route("/voice", methods=["POST"])
def voice():
    # Start conversation by asking for full name
    conversation_log.clear()
    response = (
        '<Response>'
        '<Say voice="Polly.Joanna">Hi! Thanks for calling. I\'d like to get to know you better. Can I please have your full name?</Say>'
        '<Record maxLength="10" action="/handle-response?q=0" method="POST" playBeep="false" />'
        '</Response>'
    )
    return Response(response, mimetype='text/xml')

@app.route("/handle-response", methods=["POST"])
def handle_response():
    global conversation_log, first_name, conversation_complete

    if conversation_complete:
        return Response(
            '<Response><Say>The call is complete. Thank you for your time.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    qid = int(request.args.get("q", 0))
    recording_url = request.form.get("RecordingUrl") + ".mp3"
    print("Recording URL:", recording_url)

    time.sleep(3)

    # Transcribe audio
    try:
        audio_data = requests.get(recording_url).content
        with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_data)
            tmp.flush()
        with open(tmp.name, "rb") as audio_file:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        transcript = resp.text
    except Exception as e:
        traceback.print_exc()
        print("Error during transcription:", e)
        return Response(
            '<Response><Say>Sorry, there was a technical issue understanding your answer.</Say><Hangup/></Response>',
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

    # Generate next question or closing
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
            messages=messages
        )
        next_line = chat.choices[0].message.content.strip()
    except Exception as e:
        traceback.print_exc()
        print("Error during GPT analysis:", e)
        return Response(
            '<Response><Say>Sorry, there was an issue continuing the interview. Please try again later.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    print("Next Line:", next_line)
    # Build TwiML
    if "thank you, that's all i need today" in next_line.lower():
        conversation_complete = True
        twiml = f'<Response><Say>{next_line}</Say><Hangup/></Response>'
    else:
        twiml = (
            f'<Response><Say>{next_line}</Say>'
            f'<Record maxLength="10" action="/handle-response?q={qid+1}" method="POST" playBeep="false" />'
            '</Response>'
        )
    return Response(twiml, mimetype='text/xml')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
