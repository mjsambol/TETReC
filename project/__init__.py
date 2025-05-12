##################################################################################
#
# Team Text Editing, Translation and Review Coordination tool
# Copyright (C) 2023-2025, Moshe Sambol, https://github.com/mjsambol
#
# Originally created for the Tamtzit Hachadashot / News In Brief project
# of the Lokhim Ahrayut non-profit organization
# Published in English as "Israel News Highlights"
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
#################################################################################

from flask import Flask
from google.appengine.api import wrap_wsgi_app
import sys
import os


def create_app():
    # print(f"__init__.py create_app(): path is {sys.path}")
    # print(f"CWD is {os.getcwd()}")
    # print(f"this file is {os.path.realpath(__file__)}")
    # print(f"this file is in {os.path.dirname(os.path.realpath(__file__))}")
    sys.path.append(os.path.dirname(os.path.realpath(__file__)))
    app = Flask(__name__)
    app.wsgi_app = wrap_wsgi_app(app.wsgi_app)
    app.config['SECRET_KEY'] = 'uiHvrty90p3'

    from tamtzit import tamtzit as tamtzit_blueprint
    app.register_blueprint(tamtzit_blueprint)
    print("I'm in create_app!")
    return app
