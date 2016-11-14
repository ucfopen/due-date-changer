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
@lti(error=error, request='initial', role='any', app=app)
def launch(lti=lti):
    course_id = request.form.get('custom_canvas_course_id')

    return redirect(url_for('show_assignments', course_id=course_id))


@app.route('/', methods=['GET'])
@lti(error=error, request='any', role='any', app=app)
def index(lti=lti):
    return "Please contact your System Administrator."


@app.route('/course/<course_id>/assignments', methods=['GET'])
@lti(error=error, request='any', role='any', app=app)
def show_assignments(course_id, lti=lti):
    course = canvas.get_course(course_id)
    assignments = course.get_assignments()
    for assignment in assignments:
        print assignment.name, assignment.published
    return render_template(
        'assignments.htm.j2',
        assignments=assignments,
        course=course
    )


@app.route('/lti.xml', methods=['GET'])
def xml():
    return Response(
        render_template('lti.xml.j2'),
        mimetype='text/xml'
    )


@app.template_filter()
def datetimeformat(utc_datetime, format='%m/%d/%Y %I:%M %p'):
    if not utc_datetime.tzinfo:
        # Localize to UTC if there is no timezone information.
        utc_datetime = utc.localize(utc_datetime)

    new_tz = timezone(config.TIME_ZONE)
    local_datetime = utc_datetime.astimezone(new_tz)

    return local_datetime.strftime(format)
