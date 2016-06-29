# SQLALCHEMY_DATABASE_URI = os.environ['OPENSHIFT_POSTGRESQL_DB_URL']
import re
import uuid
from datetime import datetime
from twitter import *
import boto3
from flask import Flask, request, flash, url_for, redirect, render_template, g
from flask_login import LoginManager, unicode
from flask_login import login_user, logout_user, current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_utils import UUIDType
from gtts import gTTS
# Set master account here
master = "master_account@arise-impact.org"

app = Flask(__name__)
app.config.from_pyfile('todoapp.cfg')
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = 'login'



class Doc(db.Model):
    __tablename__ = "documents"
    doc_id = db.Column('doc_id', db.Integer, primary_key=True, autoincrement=True)
    doc_title = db.Column('doc_title', db.Text)
    doc_bucket = db.Column('doc_bucket', db.Text)
    db.create_all()
    db.session.commit()

    def __init__(self, title, bucket):
        self.doc_title=title
        self.doc_bucket=bucket
    def getId(self):
        return self.doc_id

class User(db.Model):
    __tablename__ = "users"
    id = db.Column('user_id', UUIDType(binary=False), primary_key=True)
    username = db.Column('username', db.String(20), unique=True, index=True)
    password = db.Column('password', db.String(250))
    email = db.Column('email', db.String(50), unique=True, index=True)
    registered_on = db.Column('registered_on', db.DateTime)
    todos = db.relationship('Todo', backref='user', lazy='dynamic')
    org = db.Column('org', db.String(250))
    name = db.Column('name', db.String(250))
    role = db.Column('role', db.Text)

    # Note to self -Understand the index property
    db.create_all()
    db.session.commit()

    def __init__(self, username, password, email, name, org):
        self.username = username
        self.set_password(password)
        self.email = email
        self.role = self.analyzerole(master)
        self.name = name
        self.org = org
        self.registered_on = datetime.utcnow()
        self.id = uuid.uuid4()

    def analyzerole(self, m):
        if self.email is m:
            return 'master'
        elif self.email.endswith('@arise-impact.org'):
            return 'admin'
        else:
            return 'standard'

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return unicode(self.id)

    def __repr__(self):
        return '<User %r>' % (self.username)

    def OneWord(self):
        if ' ' in self.username:
            return False
        return True

    def containsSpecial(self):
        if all(x.isalpha() or x.isspace() for x in self.name):
            return False
        return True


class Todo(db.Model):
    __tablename__ = 'todos'
    id = db.Column('todo_id', db.Integer, primary_key=True)
    title = db.Column(db.String(60))
    text = db.Column(db.String)
    done = db.Column(db.Boolean)
    pub_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    db.create_all()
    db.session.commit()

    def __init__(self, title, text):
        self.title = title
        self.text = text
        self.done = False
        self.pub_date = datetime.utcnow()


def passwordValid(p):
    x = False
    while not x:
        if (len(p) < 6 or len(p) > 20):
            flash("Password is not the right length (6-20)")
            x = True
        if not re.search("[a-z]", p):
            flash("Password does not contain lower case letters!")
            x = True
        if not re.search("[0-9]", p):
            flash("Password does not contain numbers!")
            x = True
        if not re.search("[A-Z]", p):
            flash("Password does not contain upper case letters!")
            x = True
        if re.search("\s", p):
            flash("Password contains spaces!")
            x = True
        break
    return not x

@app.route('/')
@login_required
def index():
    return render_template('index.html',
                           todos=Todo.query.filter_by(user_id=g.user.id).order_by(Todo.pub_date.desc()).all()
                           )

@app.route('/todos/<int:todo_id>', methods=['GET', 'POST'])
@login_required
def show_or_update(todo_id):
    todo_item = Todo.query.get(todo_id)
    if request.method == 'GET':
        return render_template('view.html', todo=todo_item)
    if todo_item.user.id == g.user.id:
        todo_item.title = request.form['title']
        todo_item.text = request.form['text']
        todo_item.done = ('done.%d' % todo_id) in request.form
        db.session.commit()
        return redirect(url_for('index'))
    flash('You are not authorized to edit this todo item', 'error')
    return redirect(url_for('show_or_update', todo_id=todo_id))

@app.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        if not request.form['title']:
            flash('Title is required', 'error')
        elif not request.form['text']:
            flash('Text is required', 'error')
        else:
            todo = Todo(request.form['title'], request.form['text'])
            todo.user = g.user
            db.session.add(todo)
            db.session.commit()
            flash('Todo item was successfully created')
            return redirect(url_for('index'))
    return render_template('new.html')

@app.route('/mytts', methods=['GET', 'POST'])
@login_required
def mytts():
    if request.method == 'POST':
        if not request.form['text']:
            flash('Text needed to proceed', 'error')
        else:
            text_input = request.form['text']
            tts = gTTS(text=text_input, lang='en')
    return render_template('mytts.html')

@app.route('/autotweet', methods=['GET', 'POST'])
@login_required
def auto():
    #Query user's data here and check role
    if request.method == 'POST':
        if not request.form['text']:
            flash('Title is required', 'error')
        else:
            new_status=request.form['text']
            config = {}
            exec(open("twit_conf.py").read(), config)
            twit = Twitter(
                auth=OAuth(config["access_key"], config["access_secret"], config["consumer_key"], config["consumer_secret"]))
            result = twit.statuses.update(status = new_status)
            if result is True:
                flash("Tweeted successfully!")
            else:
                flash("ERROR: Tweet failed. Please try again later")
            return redirect(url_for('auto'))
    return render_template('autotweet.html')

@app.route('/directory', methods=['GET', 'POST'])
@login_required
def directory():
    return render_template('index.html',
                           documents=Doc.order_by(Doc.getId()).all()
                           )

@app.route('/directory/<string:doc_title>', methods=['GET', 'POST'])
@login_required
def showdoc(doc_id):
    doc_item = Doc.query.get(doc_id)
    if request.method == 'GET':
        return render_template('docview.html', doc=doc_item)
    flash('You are not authorized to view this file', 'error')
    return redirect(url_for('showdoc', doc_id=doc_id))
# Download feature not implemented yet


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    user = User(request.form['username'], request.form['password'], request.form['email'], request.form['name'],
                request.form['org'])
    snag = False
    if request.form['password'] != request.form['confirm']:
        snag = True
        flash('Password does not match confirmation')
    prior = User.query.filter_by(username=request.form['username']).first()
    if prior is not None:
        snag = True
        flash('Username is not unique')
    prior = User.query.filter_by(email=request.form['email']).first()
    if prior is not None:
        snag = True
        flash('This E-mail ID has already been registered!')
    if user.OneWord() is False:
        snag = True
        flash('Username has to be One Word')
    if user.containsSpecial() is True:
        snag = True
        flash('Name cannot contain Special Characters or Numbers')
    if passwordValid(request.form['password']) is False:
        snag = True
    if snag is False:
        db.session.add(user)
        db.session.commit()
        flash('User successfully registered as ' + user.role) #Remove role once confirmed as working
        return redirect(url_for('login'))
    else:
        return redirect(url_for('register'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form['username']
    password = request.form['password']
    remember_me = False
    if 'remember_me' in request.form:
        remember_me = True
    registered_user = User.query.filter_by(username=username).first()
    if registered_user is None:
        flash('Username is invalid', 'error')
        return redirect(url_for('login'))
    if not registered_user.check_password(password):
        flash('Password is invalid', 'error')
        return redirect(url_for('login'))
    login_user(registered_user, remember=remember_me)
    flash('Logged in successfully')
    return redirect(request.args.get('next') or url_for('index'))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@login_manager.user_loader
def load_user(id):
    return User.query.get(id)


@app.before_request
def before_request():
    g.user = current_user


if __name__ == '__main__':
    app.run()
