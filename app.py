iimport openai
import requests
import time
from io import BytesIO
import os
from flask import Flask, request, Response
from tempfile import NamedTemporaryFile
import traceback

openai.api_key = os.getenv("OPENAI_API_KEY")
app = Flask(__name__)

# Simple in-memory conversation tracker (reset every call)
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

    question_id = int(request.args.get("q", 0))
    recording_url = request.form.get("RecordingUrl") + ".mp3"
    caller_number = request.form.get("From", "an unknown number")
    print("Recording URL:", recording_url)

    time.sleep(3)

    try:
        audio_data = requests.get(recording_url).content
        with NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            temp_audio.write(audio_data)
            temp_audio.flush()
            with open(temp_audio.name, "rb") as audio_file:
                transcript_response = openai.Audio.transcribe("whisper-1", audio_file)
        transcript = transcript_response.get("text", "")
    except Exception as e:
        traceback.print_exc()
        print("Error during transcription:", str(e))
        return Response(
            '<Response><Say>Sorry, there was a technical issue understanding your answer.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    print("Transcript:", transcript)

    if question_id == 0:
        words = transcript.split()
        first_name = words[1] if words and words[0].lower() in ["my", "i'm", "i"] and len(words) > 1 else (words[0] if words else "there")
        conversation_log.append(f"Full name: {transcript}")
    else:
        conversation_log.append(f"{first_name}: {transcript}")

    try:
        system_prompt = (
            f"You are conducting a voice interview. Do not say you are an AI. Address the caller by their first name, {first_name}."
            f" The caller's number is {caller_number}."
            " First, confirm the number they are calling from."
            " Ask if it is their personal cell phone number."
            " Then confirm whether it is the number they would have registered with."
            " Ask if they are in our database."
            " After that, confirm their city and state, age, marital status, and if they have any children at home."
            " If they do, ask about their children's ages and genders."
            " Do not repeat questions or loop through the same topics."
            " Always ask one question at a time."
            " When the interview is done, say 'Thank you, that's all I need today.' and hang up."
        )
        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(conversation_log)}
            ]
        )
        next_line = gpt_response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        traceback.print_exc()
        print("Error during GPT analysis:", str(e))
        return Response(
            '<Response><Say>Sorry, there was an issue continuing the interview. Please try again later.</Say><Hangup/></Response>',
            mimetype='text/xml'
        )

    print("GPT Next Line:", next_line)

    if "thank you, that's all i need today" in next_line.lower():
        conversation_complete = True
        twiml = f'<Response><Say>{next_line}</Say><Hangup/></Response>'
    else:
        twiml = (
            f'<Response><Say>{next_line}</Say>'
            f'<Record maxLength="10" action="/handle-response?q={question_id+1}" method="POST" playBeep="false" />'
            '</Response>'
        )
    return Response(twiml, mimetype='text/xml')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
