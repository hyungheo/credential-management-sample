#!/usr/bin/python
# Copyright Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# coding: -*- utf-8 -*-

from google.appengine.ext import vendor
vendor.add('lib')

import os
import binascii
import json
import urllib
from bcrypt import bcrypt
from flask import Flask, request, make_response, render_template, session
from oauth2client import client

from google.appengine.ext import ndb
from google.appengine.api import urlfetch

app = Flask(
    __name__,
    static_url_path='',
    static_folder='static',
    template_folder='templates'
)
app.debug = True

CLIENT_ID = json.loads(open('client_secrets.json', 'r')
                       .read())['web']['client_id']

# On this sample, this is not really a secret
# Make sure to change SECRET_KEY for your own purposes
SECRET_KEY = 'abcde'
app.config.update(
    SECRET_KEY=SECRET_KEY
)


class CredentialStore(ndb.Model):
    profile = ndb.JsonProperty()

    @classmethod
    def remove(cls, key):
        ndb.Key(cls.__name__, key).delete()

    @classmethod
    def hash(cls, password):
        return bcrypt.hashpw(password, bcrypt.gensalt())

    @classmethod
    def verify(cls, password, hashed):
        if bcrypt.hashpw(password, hashed) == hashed:
            return True
        else:
            return False


@app.before_request
def csrf_protect():
    if request.method == 'POST':
        csrf_token = session.get('csrf_token', None)
        if not csrf_token or csrf_token != request.form.get('csrf_token'):
            return make_response('', 403)


@app.route('/')
def index():
    if 'csrf_token' not in session:
        session['csrf_token'] = binascii.hexlify(os.urandom(24))
    return render_template('index.html', client_id=CLIENT_ID,
                           csrf_token=session['csrf_token'])


@app.route('/auth/password', methods=['POST'])
def pwauth():
    email = request.form.get('email', None)
    password = request.form.get('password', None)

    store = CredentialStore.get_by_id(email)
    if store is None:
        return make_response('Authentication failed.', 401)

    profile = store.profile

    if profile is None:
        return make_response('Authentication failed.', 401)

    # Apply same hash as stored password
    if CredentialStore.verify(password, profile['password']) is False:
        return make_response('Authentication failed.', 401)

    # Get rid of password
    profile.pop('password')

    return make_response(json.dumps(profile), 200)


@app.route('/auth/google', methods=['POST'])
def gauth():

    id_token = request.form.get('id_token', '')
    idinfo = client.verify_id_token(id_token, CLIENT_ID)

    if idinfo['aud'] != CLIENT_ID:
        return make_response('Wrong Audience.', 401)
    if idinfo['iss'] not in ['accounts.google.com',
                             'https://accounts.google.com']:
        return make_response('Wrong Issuer.', 401)

    # For now, we'll always store profile data after successfully
    # verifying the token and consider the user authenticated.
    store = CredentialStore(id=idinfo['sub'], profile=idinfo)
    store.put()

    profile = {
        'id':        idinfo.get('sub', None),
        'imageUrl':  idinfo.get('picture', None),
        'name':      idinfo.get('name', None),
        'email':     idinfo.get('email', None)
    }

    return make_response(json.dumps(profile), 200)


@app.route('/auth/facebook', methods=['POST'])
def fblogin():
    access_token = request.form.get('access_token', None)

    if access_token is None:
        return make_response('Authentication failed.', 401)

    params = {
        'input_token':  access_token,
        'access_token': access_token
    }
    r = urlfetch.fetch('https://graph.facebook.com/debug_token?' +
                       urllib.urlencode(params))
    result = json.loads(r.content)

    if result['data']['is_valid'] is False:
        return make_response('Authentication failed.', 401)

    r = urlfetch.fetch('https://graph.facebook.com/me?fields=name,email',
                       headers={'Authorization': 'OAuth '+access_token})
    idinfo = json.loads(r.content)
    store = CredentialStore(id=idinfo['id'], profile=idinfo)
    store.put()

    profile = idinfo
    profile['imageUrl'] = 'https://graph.facebook.com/' + profile['id'] +\
        '/picture?width=96&height=96'

    return make_response(json.dumps(profile), 200)


@app.route('/register', methods=['POST'])
def register():
    if 'email' in request.form and 'password' in request.form \
            and len(request.form['email']) > 1 \
            and len(request.form['password']) > 1:

        # Hash password
        password = CredentialStore.hash(request.form['password'])
        # Perform relevant sanitization/validation on your own code.
        # This demo omits them on purpose for simplicity.
        profile = {
            'id':       request.form.get('email', None),
            'email':    request.form.get('email', None),
            'name':     request.form.get('name', None),
            'password': password,
            'imageUrl': 'images/default_img.png'
        }
    else:
        return make_response('Bad request', 400)

    # overwrite existing user
    store = CredentialStore(id=profile['id'], profile=profile)
    store.put()
    profile.pop('password')

    return make_response(json.dumps(profile), 200)


@app.route('/unregister', methods=['POST'])
def unregister():
    if 'id' in request.form:
        store = CredentialStore.get_by_id(request.form['id'])
        profile = store.profile
    if profile:
        CredentialStore.remove(str(request.form['id']))
        return make_response('Success', 200)
    else:
        return make_response('Failed', 400)


@app.route('/signout', methods=['POST'])
def signout():
    return make_response(json.dumps({}), 200)
