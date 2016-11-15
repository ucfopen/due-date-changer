from collections import defaultdict
from datetime import datetime
import re

from flask import Flask, redirect, render_template, request, url_for, Response
from pycanvas import Canvas
from pylti.flask import lti
from pytz import utc, timezone

import config


app = Flask(__name__)
app.config.from_object('config')

canvas = Canvas(config.API_URL, config.API_KEY)


@app.route('/error', methods=['GET'])
def error(exception=None):
    return Response(
        render_template(
            'error.htm.j2',
            messages=exception.get('exception', 'An unknown exception occured.')
        )
    )


@app.route('/launch', methods=['POST', 'GET'])
@lti(error=error, request='initial', role='staff', app=app)
def launch(lti=lti):
    course_id = request.form.get('custom_canvas_course_id')

    return redirect(url_for('show_assignments', course_id=course_id))


@app.route('/', methods=['GET'])
@lti(error=error, request='any', role='any', app=app)
def index(lti=lti):
    return "Please contact your System Administrator."


@app.route('/course/<course_id>/assignments', methods=['GET'])
@lti(error=error, request='session', role='staff', app=app)
def show_assignments(course_id, lti=lti):
    course = canvas.get_course(course_id)
    assignments = course.get_assignments()

    return render_template(
        'assignments.htm.j2',
        assignments=assignments,
        course=course
    )


@app.route('/course/<course_id>/update', methods=['POST'])
@lti(error=error, request='session', role='staff', app=app)
def update_assignments(course_id, lti=lti):
    post_data = request.form

    local_tz = timezone(config.TIME_ZONE)
    assignment_field_map = defaultdict(dict)

    for key, value in post_data.iteritems():
        if not re.match(r'\d+-[a-z_]+', key):
            continue

        assignment_id, field_name = key.split('-')

        if value is None:
            value = ''
        elif value == 'on':
            value = True
        else:
            try:
                value = datetime.strptime(value, config.LOCAL_TIME_FORMAT)
                value = local_tz.localize(value)
                value = value.isoformat()
            except ValueError:
                # Not a valid time. Just ignore.
                value = ''

        assignment_field_map[assignment_id].update({field_name: value})

    course = canvas.get_course(course_id)
    assignments = course.get_assignments()
    for assignment in assignments:
        fields = assignment_field_map.get(str(assignment.id))

        # Unchecked checkboxes are not sent to the server, so need to manually
        # set published to False if it isn't already set.
        fields['published'] = fields.get('published', False)

        if fields and isinstance(fields, dict):
            assignment.edit(assignment=fields)

    # temporarily redirecting back for debug purposes
    return redirect(url_for('show_assignments', course_id=course_id))


@app.route('/lti.xml', methods=['GET'])
def xml():
    return Response(
        render_template('lti.xml.j2'),
        mimetype='text/xml'
    )


@app.template_filter()
def utc_datetime_to_local_str(utc_datetime, format=config.LOCAL_TIME_FORMAT):
    if not utc_datetime.tzinfo:
        # Localize to UTC if there is no timezone information.
        utc_datetime = utc.localize(utc_datetime)

    new_tz = timezone(config.TIME_ZONE)
    local_datetime = utc_datetime.astimezone(new_tz)

    return local_datetime.strftime(format)
