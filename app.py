import openai
import requests
import time
from io import BytesIO
import os
from flask import Flask, request, Response
from tempfile import NamedTemporaryFile
import traceback

# Load API key from environment
openai.api_key = os.getenv("OPENAI_API_KEY")
app = Flask(__name__)

# In-memory conversation state
conversation_log = []
first_name = ""
conversation_complete = False

@app.route("/voice", methods=["POST"])
def voice():
    caller_number = request.form.get("From", "an unknown number")
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
    rpt_url = request.form.get("RecordingUrl") + ".mp3"
    print("Recording URL:", rpt_url)

    time.sleep(3)
    transcript = ""
    try:
        # download audio
        data = requests.get(rpt_url).content
        # write to temp file
        with NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(data)
            f.flush()
            # use new OpenAI v1 transcription API
            audio_file = open(f.name, "rb")
            resp = openai.Audio.transcriptions.create(
                file=audio_file,
                model="whisper-1"
            )
        transcript = resp["text"]
    except Exception as e:
        traceback.print_exc()
        print("Error during transcription:", e)
        return Response(
            '<Response><Say>Sorry, there was a technical issue understanding your answer.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    print("Transcript:", transcript)
    # record response
    if qid == 0:
        parts = transcript.split()
        first_name = parts[1] if parts and parts[0].lower() in ["my","i'm","i"] and len(parts)>1 else (parts[0] if parts else "there")
        conversation_log.append(f"Full name: {transcript}")
    else:
        conversation_log.append(f"{first_name}: {transcript}")

    # GPT response
    try:
        system_prompt = (
            f"You are an interviewer; do not say you are AI. Call them {first_name}."
            f" Caller number: {request.form.get('From')}.")
        messages = [
            {"role":"system","content":system_prompt},
            {"role":"user","content":"\n".join(conversation_log)}
        ]
        gresp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        next_line = gresp.choices[0].message.content.strip()
    except Exception as e:
        traceback.print_exc()
        print("Error during GPT analysis:", e)
        return Response(
            '<Response><Say>Sorry, trouble continuing. Try again later.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    print("Next:", next_line)
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

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
