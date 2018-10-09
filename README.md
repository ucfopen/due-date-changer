# Due Date Changer

An LTI that allows a user to easily change due dates for multiple assignments simultaneously.

## Table of Contents

* [Installation](#installation)
* [Running the Development Server](#running-the-development-server)
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

## Running the Development Server

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

## Contact Us

Need help? Have an idea? Just want to say hi? Come join us on the [UCF Open Slack Channel](https://ucf-open-slackin.herokuapp.com) and join the `#due-date-changer` channel!
