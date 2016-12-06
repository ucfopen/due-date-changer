from collections import defaultdict
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import re

from flask import Flask, redirect, render_template, request, url_for, Response
from pycanvas import Canvas
from pycanvas.exceptions import CanvasException
from pylti.flask import lti
from pytz import utc, timezone

import config


app = Flask(__name__)
app.config.from_object('config')

formatter = logging.Formatter(config.LOG_FORMAT)
handler = RotatingFileHandler(
    config.LOG_FILE,
    maxBytes=config.LOG_MAX_BYTES,
    backupCount=config.LOG_BACKUP_COUNT
)
handler.setLevel(logging.getLevelName(config.LOG_LEVEL))
handler.setFormatter(formatter)
app.logger.addHandler(handler)

canvas = Canvas(config.API_URL, config.API_KEY)


def error(exception=None):
    return Response(
        render_template(
            'error.htm.j2',
            message=exception.get(
                'exception',
                'Please contact your System Administrator.'
            )
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
    try:
        course = canvas.get_course(course_id)
        assignments = course.get_assignments()
        quiz_dict = {quiz.id: quiz for quiz in course.get_quizzes()}
    except CanvasException as err:
        app.logger.exception('Error getting assignments from Canvas.')
        return error({'exception': err})

    assignment_quiz_list = []
    for assignment in assignments:
        if hasattr(assignment, 'quiz_id'):
            quiz = quiz_dict.get(assignment.quiz_id)
            if hasattr(quiz, 'show_correct_answers_at_date'):
                assignment.show_correct_answers_at_date = utc_datetime_to_local_str(
                    quiz.show_correct_answers_at_date
                )
            if hasattr(quiz, 'hide_correct_answers_at_date'):
                assignment.hide_correct_answers_at_date = utc_datetime_to_local_str(
                    quiz.hide_correct_answers_at_date
                )
        assignment_quiz_list.append(assignment)

    return render_template(
        'assignments.htm.j2',
        assignments=assignment_quiz_list,
        course=course
    )


@app.route('/course/<course_id>/update', methods=['POST'])
@lti(error=error, request='session', role='staff', app=app)
def update_assignments(course_id, lti=lti):

    def fix_date(value):
        try:
            value = datetime.strptime(value, config.LOCAL_TIME_FORMAT)
            value = local_tz.localize(value)
            return value.isoformat()
        except ValueError:
            # Not a valid time. Just ignore.
            return ''

    def error_json(assignment_id, updated_list):
        msg = 'There was an error editing one of the assignments. (ID: {})'
        msg.format(assignment_id)
        if len(updated_list) > 0:
            msg += ' {} assignments have been updated successfully.'.format(
                len(updated_list)
            )

        return json.dumps({
            'error': True,
            'message': msg,
            'updated': updated_list,
        })

    if not request.is_xhr:
        return render_template('error.htm.j2', message='Non-AJAX requests not allowed.')

    post_data = request.form

    local_tz = timezone(config.TIME_ZONE)
    assignment_field_map = defaultdict(dict)

    for key, value in post_data.iteritems():
        if not re.match(r'\d+-[a-z_]+', key):
            continue

        assignment_id, field_name = key.split('-')
        assignment_field_map[assignment_id].update({field_name: value})

    updated_list = []
    for assignment_id, field in assignment_field_map.iteritems():
        assignment_type = field.get('assignment_type', 'assignment')
        quiz_id = field.get('quiz_id')
        try:
            course = canvas.get_course(course_id)
        except CanvasException:
            app.logger.exception('Error getting course #{}.'.format(course_id))

        payload = {
            'published': True if field.get('published') == 'on' else False,
            'due_at': fix_date(field.get('due_at')),
            'lock_at': fix_date(field.get('lock_at')),
            'unlock_at': fix_date(field.get('unlock_at')),
        }

        if assignment_type == 'quiz' and quiz_id:
            payload.update({
                'show_correct_answers_at': fix_date(
                    field.get('show_correct_answers_at')
                ),
                'hide_correct_answers_at': fix_date(
                    field.get('hide_correct_answers_at')
                )
            })

            try:
                quiz = course.get_quiz(quiz_id)
                quiz.edit(quiz=payload)
                updated_list.append({
                    'id': assignment_id,
                    'title': quiz.title,
                    'type': 'Quiz'
                })
            except CanvasException:
                app.logger.exception('Error getting/editing quiz #{}.'.format(
                    quiz_id
                ))

                return error_json(assignment_id, updated_list)

        else:
            try:
                assignment = course.get_assignment(assignment_id)
                assignment.edit(assignment=payload)
                updated_list.append({
                    'id': assignment_id,
                    'title': assignment.name,
                    'type': 'Assignment'
                })
            except CanvasException:
                app.logger.exception('Error getting/editing assignment #{}.'.format(
                    assignment_id
                ))

                return error_json(assignment_id, updated_list)

    return json.dumps({
        'error': False,
        'message': 'Successfully updated {} assignments.'.format(len(updated_list)),
        'updated': updated_list,
    })


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
