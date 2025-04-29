from openai import OpenAI
import requests
import time
from io import BytesIO
import os
import shutil
from flask import Flask, request, Response, session, render_template, redirect, url_for, flash, jsonify
from tempfile import NamedTemporaryFile
import traceback
from contextlib import contextmanager
import json
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Initialize OpenAI client using environment variable from Render
api_key = os.getenv('Render')
if not api_key:
    raise ValueError("Render environment variable (OpenAI API key) is not set. Please check your Render environment configuration.")

# Initialize Flask and its extensions
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
# Use in-memory SQLite for Render deployment
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FRONTEND_URL'] = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

client = OpenAI(api_key=api_key)

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

# Define roles and their permissions
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    permissions = db.Column(db.String(500))  # JSON string of permissions

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref='users')
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        if not self.role:
            return False
        permissions = self.role.permissions.split(',')
        return permission in permissions

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom decorator for role-based access control
def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role.name != role_name:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Create database and default roles/users if they don't exist
with app.app_context():
    db.create_all()
    
    # Create default roles if they don't exist
    roles = {
        'admin': 'Full access to all features and user management',
        'manager': 'Access to analytics and basic management features',
        'user': 'Basic access to core features'
    }
    
    for role_name, description in roles.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name, description=description)
            if role_name == 'admin':
                role.permissions = 'admin,manage_users,sheet_search,questionnaire_bot,analytics'
            elif role_name == 'manager':
                role.permissions = 'sheet_search,questionnaire_bot,analytics'
            else:
                role.permissions = 'sheet_search,questionnaire_bot'
            db.session.add(role)
    
    # Create admin user if it doesn't exist
    admin_role = Role.query.filter_by(name='admin').first()
    if admin_role:
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', role=admin_role)
            admin.set_password('admin')  # Change this password in production
            db.session.add(admin)
    
    db.session.commit()

# Helper functions for call agent
def save_conversation(call_sid, conversation_data):
    """Save conversation data to a file for future reference."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{CONVERSATION_STORAGE_DIR}/{call_sid}_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(conversation_data, f, indent=2)

def load_conversation(call_sid):
    """Load conversation data if it exists."""
    try:
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
    """Extract name and preferred name from transcript."""
    if not transcript:
        return "there", None
    
    words = transcript.strip().lower().split()
    if not words:
        return "there", None
    
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
    
    transcript_lower = transcript.lower()
    for pattern, skip in intro_patterns.items():
        if pattern in transcript_lower:
            parts = transcript_lower.split(pattern, 1)
            if len(parts) > 1:
                name_parts = parts[1].strip().split()
                if name_parts:
                    preferred_name = None
                    if "but" in name_parts or "however" in name_parts:
                        for i, word in enumerate(name_parts):
                            if word in ["but", "however"] and i + 1 < len(name_parts):
                                preferred_name = name_parts[i + 1]
                                break
                    return name_parts[0], preferred_name
    
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

# Web routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account is inactive. Please contact an administrator.')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/sheet-search')
@login_required
def sheet_search():
    if not current_user.has_permission('sheet_search'):
        flash('You do not have permission to access this feature.', 'error')
        return redirect(url_for('dashboard'))
    # Redirect to the React frontend's sheet search page
    frontend_url = app.config['FRONTEND_URL']
    return redirect(f'{frontend_url}/sheet-search')

@app.route('/questionnaire-bot')
@login_required
def questionnaire_bot():
    if not current_user.has_permission('questionnaire_bot'):
        flash('You do not have permission to access this feature.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('questionnaire_bot.html')

# Admin routes
@app.route('/admin/users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.all()
    roles = Role.query.all()
    return render_template('admin/users.html', users=users, roles=roles)

@app.route('/admin/user/<int:user_id>', methods=['GET'])
@login_required
@role_required('admin')
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'role_id': user.role_id,
        'is_active': user.is_active
    })

@app.route('/admin/user/update', methods=['POST'])
@login_required
@role_required('admin')
def update_user():
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    user.username = request.form.get('username')
    user.role_id = request.form.get('role')
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/user/<int:user_id>/activate', methods=['POST'])
@login_required
@role_required('admin')
def activate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/user/<int:user_id>/deactivate', methods=['POST'])
@login_required
@role_required('admin')
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    return jsonify({'success': True})

# Call agent routes
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get('CallSid', 'unknown')
    
    session['call_sid'] = call_sid
    session['conversation_log'] = []
    session['first_name'] = ""
    session['preferred_name'] = None
    session['conversation_complete'] = False
    
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

    max_retries = 3
    retry_delay = 5
    last_error = None
    
    for attempt in range(max_retries):
        try:
            time.sleep(retry_delay)
            response = requests.get(recording_url, timeout=15)
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
                retry_delay *= 2
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
    
    conversation_data = {
        'call_sid': call_sid,
        'conversation_log': conversation_log,
        'first_name': session.get('first_name'),
        'preferred_name': session.get('preferred_name'),
        'timestamp': datetime.now().isoformat()
    }
    save_conversation(call_sid, conversation_data)

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

@app.route('/api/sheet-search')
@login_required
def api_sheet_search():
    try:
        # Initialize Google Drive API
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        if not SERVICE_ACCOUNT_FILE:
            return jsonify({'error': 'Google credentials not configured'}), 500
            
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=credentials)
        
        # Search for files containing "(Survey) (Responses)"
        query = "name contains '(Survey) (Responses)' and mimeType='application/vnd.google-apps.spreadsheet'"
        results = service.files().list(
            q=query,
            fields="files(id, name, createdTime, modifiedTime)",
            orderBy="createdTime"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return jsonify({
                'total_sheets': 0,
                'oldest_created': None,
                'newest_modified': None,
                'files': []
            })
        
        # Process files
        processed_files = []
        oldest_created = None
        newest_modified = None
        
        for file in files:
            created_time = datetime.fromisoformat(file['createdTime'].replace('Z', '+00:00'))
            modified_time = datetime.fromisoformat(file['modifiedTime'].replace('Z', '+00:00'))
            
            if oldest_created is None or created_time < oldest_created:
                oldest_created = created_time
            if newest_modified is None or modified_time > newest_modified:
                newest_modified = modified_time
                
            processed_files.append({
                'name': file['name'],
                'created': created_time.strftime('%Y-%m-%d')
            })
        
        return jsonify({
            'total_sheets': len(files),
            'oldest_created': oldest_created.strftime('%Y-%m-%d') if oldest_created else None,
            'newest_modified': newest_modified.strftime('%Y-%m-%d') if newest_modified else None,
            'files': processed_files
        })
        
    except HttpError as error:
        return jsonify({'error': f'Google API error: {str(error)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
