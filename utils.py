# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from datetime import datetime

from pytz import timezone

import config


def fix_date(value):
    local_tz = timezone(config.TIME_ZONE)
    try:
        value = datetime.strptime(value, config.LOCAL_TIME_FORMAT)
        value = local_tz.localize(value)
        return value.isoformat()
    except (ValueError, TypeError):
        # Not a valid time. Just ignore.
        return ""


def update_job(job, percent, status_msg, status, error=False):
    """
    Update job status.
    """
    job.meta["percent"] = percent
    job.meta["status"] = status
    job.meta["status_msg"] = status_msg
    job.meta["error"] = error

    job.save()
