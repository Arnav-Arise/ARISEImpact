# SQLALCHEMY_DATABASE_URI = os.environ['OPENSHIFT_POSTGRESQL_DB_URL']
import os
from datetime import datetime
from tempfile import TemporaryFile

from boto.s3.key import Key
import boto
import facebook
import flask
import re
import uuid
from PyLinkedinAPI.PyLinkedinAPI import PyLinkedinAPI
from flask import Flask, request, flash, url_for, redirect, render_template, g
from flask_login import LoginManager, unicode
from flask_login import login_user, logout_user, current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from gtts import gTTS
from sqlalchemy_utils import UUIDType
from twitter import *
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_from_directory

# master account address here
from werkzeug.utils import secure_filename

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
        self.doc_title = title
        self.doc_bucket = bucket

    def getId(self):
        return self.doc_id

    def getbucketname(self):
        return self.doc_bucket


class User(db.Model):
    __tablename__ = "users"
    id = db.Column('user_id', UUIDType(binary=False), primary_key=True)
    username = db.Column('username', db.String(20), unique=True, index=True)
    password = db.Column('password', db.String(250))
    email = db.Column('email', db.String(50), unique=True, index=True)
    registered_on = db.Column('registered_on', db.DateTime)
    todos = db.relationship('Todo', backref='User', lazy='dynamic')
    org = db.Column('org', db.String(250))
    name = db.Column('name', db.String(250))
    role = db.Column('role', db.Text)

    # Understand index property
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

    def oneword(self):
        if ' ' in self.username:
            return False
        return True

    def get_role(self):
        return self.role

    def contains_special(self):
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
    if request.method == 'GET':
        return render_template('new.html')
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
            return redirect(url_for('mytts'))
        else:
            text_input = request.form['text']
            tts = gTTS(text=text_input, lang=request.form['lang'])
            tts.save("output.mp3")
            return flask.send_file('output.mp3', as_attachment=True)
    return render_template('mytts.html')


# Auto-post section begins here
'''How to get credentials for LinkedIn: You need to generate temporary access token for basic tests:
•Access the https://developer.linkedin.com/rest-console
•On then Authentication menu select OAuth2
•After you need to login and authorization to access some sainformation from your LinkedIn proﬁle
•Send anywhere request URL, for examplehttps://api.linkedin.com/v1/people/~?format=json, and copy ﬁeld access token
'''

'''How to get credentials for FB: create a Facebook App which will be used to access Facebook's Graph API. Go to
Facebook Apps dashboard -> Click Add a New App -> Choose platform WWW -> Choose a new name for your app -> Click Create
New Facebook App ID -> Create a New App ID -> Choose Category (I chose "Entertainment") -> Click Create App ID again. Go
back to Apps dashboard -> Select the new app -> Settings -> Basic -> Enter Contact Email.
This is required to take your app out of the sandbox. Go to Status & Review -> Do you want to make this app and all its
live features available to the general public? -> Toggle the button to Yes -> Make App Public? -> Yes. This will enable
others to see posts by your app in their timelines - otherwise, only you will see the wall posts by the app.
Make a note of the App ID and App Secret '''

'''
    CODE TO IMPORT medium_conf details
    Issue - Don't know how to retrieve content :-/
        conf={}
        exec(open("medium_conf.py").read(), conf)
        client=Client(application_id=conf["application_id"], application_secret=conf["application_secret"])

        #Delete lines below if access token is already present
        auth_url = client.get_authorization_url("secretstate", conf["redirect_url"],
                                               ["basicProfile", "publishPost"])
        auth = client.exchange_authorization_code("YOUR_AUTHORIZATION_CODE", conf["redirect_url"])

        client.access_token = auth["access_token"]
        user = client.get_current_user()
'''


@app.route('/autopost', methods=['GET', 'POST'])
@login_required
def auto():
    # Code for checking ROLE and validation
    # registered_user = User.query.filter_by(id=g.user.id).first()
    # if registered_user.get_role() is not 'admin':
    # flash('You are not authorized to use this feature')
    # return redirect(url_for('index'))

    if request.method == 'GET':
        flash('')
    # Alternate method for Medium
    # Get JSON info from https://www.medium.com/@handlename/latest?format=json
    # handle = "myhandle"
    # article.name = <Get name of article>
    # article.id = <Get post id>
    # article.name = article.name.lstrip()
    # article.name = article.name.lower()
    # article.name.replace(' ', '-')
    # url= 'https://www.medium.com/'+ handle + '/' + article.name + '-' +article.id
    # return render_template('autopost.html' url=url)
    # Adjust textarea in autopost.html to set some default text, involving {{ url }}
    # NOTE - The JSON info does not contain NAME.
    # One source suggested the use of Kimono API generator to extract the name as a property

    if request.method == 'POST':
        if not request.form['text']:
            flash('Title is required', 'error')
        else:
            new_status = request.form['text']
            checked = False
            if 'Twitter' in request.form:
                checked = True
                config = {}
                exec(open("twit_conf.py").read(), config)
                twit = Twitter(
                    auth=OAuth(config["access_key"], config["access_secret"], config["consumer_key"],
                               config["consumer_secret"]))
                result = twit.statuses.update(status=new_status)
                if result is True:
                    flash("Tweeted successfully!")
                else:
                    flash("ERROR: Tweet failed. Please try again later")
            if 'Facebook' in request.form:
                checked = True
                config = {}
                exec(open("fb_conf.py").read(), config)
                graph = facebook.GraphAPI(config['access_token'])
                resp = graph.get_object('me/accounts')
                page_access_token = None
                for page in resp['data']:
                    if page['id'] == config['page_id']:
                        page_access_token = page['access_token']
                graph = facebook.GraphAPI(page_access_token)
                status = graph.put_wall_post(new_status)
                flash("Posted on Facebook successfully!")
                # Need to handle exceptions here to get an error message.
            if 'LinkedIn' in request.form:
                checked = True
                config = {}
                exec(open("lin_conf.py").read(), config)
                linkedin = PyLinkedinAPI(config['access_token'])
                linkedin.publish_profile_comment(new_status)
                # Need to handle exceptions here to get an error message.
                flash("Posted on LinkedIn successfully!")
            if checked is False:
                flash('Please select at least one checkbox', 'error')
        return redirect(url_for('auto'))
    return render_template('autopost.html')


# All S3 Bucket related functions
s3_conf = {}
exec(open("s3bucket_conf.py").read(), s3_conf)


# Fills DB with bucket contents
# Might have to check for already existing entries
def update_docs_db(bucket_name, config):
    s3 = boto.connect_s3(config['AWS_ACCESS_KEY_ID'], config['AWS_SECRET_ACCESS_KEY'])
    for bucket in s3.get_bucket(bucket_name):
        for file in bucket.list():
            doc = Doc(str(file.key), bucket.name)
            db.session.add(doc)
            db.session.commit()
    return Doc.query.filter_by(doc_bucket=bucket_name).order_by(Doc.doc_id).all()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in s3_conf['ALLOWED_EXTENSIONS']


def bucket_type(name):
    ext = name.rsplit('.', 1)[1]
    if ext is 'pdf':
        return s3_conf['PDF_BUCKET']
    elif ext is 'mp3' or ext is 'ogg':
        return s3_conf['PDF_BUCKET']
    elif ext is 'mp4':
        return s3_conf['VIDEO_BUCKET']


def gettype(bucket_name):
    if bucket_name is s3_conf['PDF_BUCKET']:
        return 'pdf_directory'
    if bucket_name is s3_conf['AUDIO_BUCKET']:
        return 'audio_directory'
    if bucket_name is s3_conf['VIDEO_BUCKET']:
        return 'video_directory'
    if bucket_name is s3_conf['SEM_BUCKET']:
        return 'sem_directory'


# Main directory - 4 pic icons for the 4 buckets and an option to upload a file
# File uploaded automatically goes to required bucket and view of that sub-directory opens
@app.route('/directory', methods=['GET', 'POST'])
@login_required
def directory():
    if request.method == 'POST':
        file = request.files['fileToUpload']
        if file and allowed_file(file.filename):  # Checks if a file has been attached, and of valid extension
            filename = secure_filename(file.filename)  # Removes forbidden characters
            file.save(os.path.join(s3_conf['UPLOAD_FOLDER'], filename))
            bucket_name = bucket_type(filename)
            if 'sem_check' in request.form:
                bucket_name = '%s' % (s3_conf['SEM_BUCKET'])
            # Catch an exception here onwards
            s3 = boto.connect_s3(s3_conf['AWS_ACCESS_KEY_ID'], s3_conf['AWS_SECRET_ACCESS_KEY'])
            namestring = '%s.' % bucket_name
            bucket = s3.get_bucket(namestring.lower())
            k = Key(bucket)
            k.key = filename
            k.set_contents_from_filename(filename)  # Path probably needed here
            k.make_public()  # Otherwise, the file will not be accessible by apps other than S3 Amazon
            os.remove(filename)
            func = gettype(bucket_name)  # Gets name of the function  to reditect to
            return redirect(url_for(func))
        else:
            flash('File type not allowed or file does not exist')
            return redirect(url_for('directory'))
    if request.method == 'GET':
        return render_template('directory.html')


# Sub-directory sections begins here
@app.route('/directory/pdf', methods=['GET', 'POST'])
@login_required
def pdf_directory():
    return render_template('sub-directory.html',
                           documents=update_docs_db(s3_conf['PDF_BUCKET'], s3_conf)
                           )


# Since an audio player can be placed in the same doc as the directory, the sub-directory is different for Audio &SEMs
@app.route('/directory/audio', methods=['GET', 'POST'])
@login_required
def audio_directory():
    return render_template('audio-player.html',
                           documents=update_docs_db(s3_conf['AUDIO_BUCKET'], s3_conf)
                           )


@app.route('/directory/video', methods=['GET', 'POST'])
@login_required
def video_directory():
    return render_template('sub-directory.html',
                           documents=update_docs_db(s3_conf['VIDEO_BUCKET'], s3_conf)
                           )


@app.route('/directory/sem', methods=['GET', 'POST'])
@login_required
def sem_directory():
    return render_template('audio-player.html',
                           documents=update_docs_db(s3_conf['SEM_BUCKET'], s3_conf)
                           )


# View Loader for PDF and Video.
@app.route('/directory/<string:doc_bucket>/<string:doc_title>', methods=['GET', 'POST'])
@login_required
def showdoc(doc_bucket, doc_title):
    doc_item = Doc.query.get(doc_title)
    doc_bucket = doc_item.getbucketname()
    if request.method == 'GET':
        conn = boto.connect_s3(s3_conf['AWS_ACCESS_KEY_ID'], s3_conf['AWS_SECRET_ACCESS_KEY'])
        bucket = conn.get_bucket(doc_bucket)
        for l in bucket.list():
            if str(l.key) is doc_title:
                l.get_contents_to_filename(s3_conf['DWNLD_FOLDER'] + doc_title)
                if doc_bucket is s3_conf['PDF_BUCKET']:
                    return render_template('doc-view.html', doc=doc_item)
                elif doc_bucket is s3_conf['VIDEO_BUCKET']:
                    return render_template('video-player.html', doc=doc_item)
            else:
                continue
        flash('The file does not exist')
        if doc_bucket is s3_conf['PDF_BUCKET']:
            return render_template('doc-view.html', doc=doc_item)
        elif doc_bucket is s3_conf['VIDEO_BUCKET']:
            return render_template('video-player.html', doc=doc_item)
    flash('You are not authorized to view this file', 'error')
    return redirect(url_for('showdoc', doc_bucket=doc_bucket, doc_title=doc_title))


# Registration section begins here
def passwordvalid(p):
    x = False
    while not x:
        if len(p) < 6 or len(p) > 20:
            flash("Password is not the right length (6-20)")
            x = True
        if not re.search('[a-z]', p):
            flash("Password does not contain lower case letters!")
            x = True
        if not re.search('[0-9]', p):
            flash("Password does not contain numbers!")
            x = True
        if not re.search('[A-Z]', p):
            flash("Password does not contain upper case letters!")
            x = True
        if re.search('\s', p):
            flash("Password contains spaces!")
            x = True
        break
    return not x


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
    if user.oneword() is False:
        snag = True
        flash('Username has to be One Word')
    if user.contains_special() is True:
        snag = True
        flash('Name cannot contain Special Characters or Numbers')
    if passwordvalid(request.form['password']) is False:
        snag = True
    if snag is False:
        db.session.add(user)
        db.session.commit()
        flash('User successfully registered as ' + user.role)  # Remove role once confirmed as working
        return redirect(url_for('login'))
    else:
        return redirect(url_for('register'))


@app.route('/forgotpassword', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot-password.html')
    email = request.form['email']
    if User.query.filter_by(email=email).first():
        # Send e-mail
        flash('Recovery e-mail has been sent to your id')
        return redirect(url_for('login'))
    else:
        flash('This e-mail has not been registered! Please register here.')
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
