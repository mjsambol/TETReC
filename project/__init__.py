from flask import Flask, url_for
#from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

##
# This code is taken from
# https://www.digitalocean.com/community/tutorials/how-to-add-authentication-to-your-app-with-flask-login
# and then modified to my needs.
#
# To package it and transfer it to the server where it will run: from the parent directory:
# tar --exclude="__pycache__" --exclude="venv" --exclude=".git" -cvzf training-admin.tgz lightrun-training-admin/
# scp -i /home/moshe/cloud/AWS/moshes-aws-2.pem training-admin.tgz ubuntu@ec2-54-241-230-139.us-west-1.compute.amazonaws.com:~
##

# init SQLAlchemy so we can use it later in our models
#db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = 'uiHvrty90p3'
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'

    # db.init_app(app)
    # with app.app_context():
    #     db.create_all()

    # login_manager = LoginManager()
    # login_manager.login_view = 'auth.login'
    # login_manager.init_app(app)

    # from .models import User

    # @login_manager.user_loader
    # def load_user(user_id):
    #     # since the user_id is just the primary key of our user table, use it in the query for the user
    #     return User.query.get(int(user_id))

    # blueprint for auth routes in our app
    # from .auth import auth as auth_blueprint
    # app.register_blueprint(auth_blueprint)

    # blueprint for non-auth parts of app
    from .tamtzit import tamtzit as tamtzit_blueprint
    app.register_blueprint(tamtzit_blueprint)
    print("I'm in create_app!")
    return app