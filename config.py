# -*- coding: utf-8 -*-
import os
from __future__ import unicode_literals

DEBUG = False
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGEME") # A secret key used by Flask for signing. KEEP THIS SECRET! (e.g. 'JbwLnLgsfxDInozQudc6IFPe0eYecW8f')

ALLOWED_CANVAS_DOMAINS = os.environ.get("ALLOWED_CANVAS_DOMAINS", ['canvas.instructure.com'])  # A list of domains that are allowed to use the tool. (e.g. ['example.com', 'example.edu'])

CANVAS_URL = os.environ.get("CANVAS_URL", "https://changeme.example.com")  # Canvas Instance URL ex. `https://example.instructure.com`
API_KEY = os.environ.get("API_KEY", "CHANGEME")  # Canvas API Key

PYLTI_CONFIG = {
    'consumers': {
        os.environ.get("LTI_KEY", "CHANGEME"): {  # consumer key
            'secret': os.environ.get("LTI_SECRET", "CHANGEME")
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
LOG_LEVEL = 'WARNING'
LOG_MAX_BYTES = 1024 * 1024 * 5  # 5 MB
LOG_BACKUP_COUNT = 1
