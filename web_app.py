from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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

# Routes
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
    return render_template('sheet_search.html')

@app.route('/questionnaire-bot')
@login_required
def questionnaire_bot():
    if not current_user.has_permission('questionnaire_bot'):
        flash('You do not have permission to access this feature.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('questionnaire_bot.html')

# Admin routes for user management
@app.route('/admin/users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

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

if __name__ == '__main__':
    app.run(debug=True) 