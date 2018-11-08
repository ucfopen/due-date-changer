# Due Date Changer

An LTI that allows a user to easily change due dates for multiple assignments simultaneously.

## Table of Contents

* [Installation](#installation)
* [Development Server](#development-server)
* [Production Server](#production-server)
* [Contributing](#contributing)
* [Contact Us](#contact-us)

## Installation

Clone the repository

```sh
# clone via SSH
git clone git@github.com:ucfopen/due-date-changer.git
```

```sh
# clone via HTTPS
git clone https://github.com/ucfopen/due-date-changer.git
```

Switch into the new directory

```sh
cd due-date-changer
```

Create the config file from the template

```sh
cp config.py.template config.py
```

Fill in the config file

```python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

DEBUG = False
SECRET_KEY = 'JbwLnLgsfxDInozQudc6IFPe0eYecW8f'

ALLOWED_CANVAS_DOMAINS = ['example.com', 'example.edu']

CANVAS_URL = 'https://example.instructure.com'
API_KEY = 'p@$$w0rd'

PYLTI_CONFIG = {
    'consumers': {
        'consumer_key': {
            'secret': b'shared_secret'
        }
    },
    'roles': {
        'staff': [
            'urn:lti:instrole:ims/lis/Administrator',
            'Instructor',
            'ContentDeveloper',
            'urn:lti:role:ims/lis/TeachingAssistant'
        ]
    }
}

TIME_ZONE = 'US/Eastern'
LOCAL_TIME_FORMAT = '%m/%d/%Y %I:%M %p'

LOG_FILE = 'due_date_changer.log'
LOG_FORMAT = '%(asctime)s [%(levelname)s] {%(filename)s:%(lineno)d} %(message)s'
LOG_LEVEL = 'DEBUG'
LOG_MAX_BYTES = 1024 * 1024 * 5  # 5 MB
LOG_BACKUP_COUNT = 1
```

Create a virtual environment

```sh
virtualenv -p python2.7 env
```

Source the environment

```sh
source env/bin/activate
```

Alternatively, use the setup script

```sh
source setup.sh
```

Install required packages

* If you want to be able to run tests:

  ```sh
  pip install -r test_requirements.txt
  ```

* Otherwise,

  ```sh
  pip install -r requirements.txt
  ```

## Development Server

If you haven't already, activate the virtual environment and set up Flask
environment variables.

```sh
source env/bin/activate
export FLASK_APP=lti.py
export FLASK_DEBUG=1
```

Alternatively, use the setup script

```sh
source setup.sh
```

Run the Flask development server.

```sh
flask run --with-threads
```

Check the status page at `/status` ([http://127.0.0.1:5000/status](http://127.0.0.1:5000/status) by default) to see if everything is
working properly.

*Note: for the status page to work, the app must be run with threading enabled.*

Ensure Redis is running. If not, start it with

```sh
redis-server --daemonize yes
```

Ensure RQ Worker is running. If not, start it with

```sh
rq worker ddc
```

## Production Server

Due Date Changer is tested to run NGINX and uWSGI, but can also work on Apache and mod_wsgi.

### NGINX

`nginx.conf`

In your nginx.conf file, place these lines under the server{} section with the appropriate changes

```nginx
location /due_date_changer/static {
    alias /path/to/due_date_changer/static/;
}


location /due_date_changer {
    root html;
    include uwsgi_params;

    uwsgi_param                  UWSGI_SCHEME https; # Set to https is behind load balancer, else http
    uwsgi_param                  SCRIPT_NAME /due_date_changer;
    uwsgi_modifier1              30;
    uwsgi_pass                   127.0.0.1:9000;  #set to any number above 9000 that isn't in use.
    uwsgi_read_timeout           300;
    uwsgi_connect_timeout        300;
    uwsgi_send_timeout           300;
    proxy_redirect               off;
    proxy_set_header             Host $host;
    proxy_set_header             X-Real-IP $remote_addr;
    proxy_set_header             X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header             X-Forwarded-Host example.com; #Add your domain here.
}
```

### UWSGI

`/etc/uwsgi/sites-enabled/due_date_changer.ini`

```ini
[uwsgi]
# uwsgi process runs as user:group
uid = nginx
gid = nginx

# Number of worker processes
processes = 6

chdir = /path/to/due_date_changer/
venv = /path/to/due_date_changer/env


socket = 127.0.0.1:9000 #Same Socket number as above

# Respawn slow processes
harakiri=60
harakiri-verbose=True

master=True

# name of wsgi file in the chdir dir above without the .py extension
wsgi-file = wsgi.py

# Background the process (and allow it to log!)
daemonize = /var/log/uwsgi/app.log

# Reload the uwsgi process if the wsgi file is touched
touch-reload = /path/to/due_date_changer/wsgi.py

#testing saveSnapshot fix
buffer-size=16384
#post-buffering=1

#stats
stats = /tmp/wsgi.py.socket
```

## Contact Us

Need help? Have an idea? Just want to say hi? Come join us on the [UCF Open Slack Channel](https://ucf-open-slackin.herokuapp.com) and join the `#due-date-changer` channel!
