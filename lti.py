from collections import defaultdict
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import re

from flask import Flask, redirect, render_template, request, url_for, Response
from canvasapi import Canvas
from canvasapi.user import User
from canvasapi.exceptions import CanvasException
from pylti.flask import lti
from pytz import utc, timezone
import requests
import six

from config import (
    ALLOWED_CANVAS_DOMAINS,
    API_KEY,
    CANVAS_URL,
    LOCAL_TIME_FORMAT,
    LOG_BACKUP_COUNT,
    LOG_FORMAT,
    LOG_FILE,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    TIME_ZONE,
)

app = Flask(__name__)
app.config.from_object("config")

formatter = logging.Formatter(LOG_FORMAT)
handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
)
handler.setLevel(logging.getLevelName(LOG_LEVEL))
handler.setFormatter(formatter)
app.logger.addHandler(handler)


canvas = Canvas(CANVAS_URL, API_KEY)


def error(exception=None):
    return Response(
        render_template(
            "error.htm.j2",
            message=exception.get(
                "exception", "Please contact your System Administrator."
            ),
        )
    )


@app.route("/launch", methods=["GET", "POST"])
@lti(error=error, request="initial", role="staff", app=app)
def launch(lti=lti):
    canvas_domain = request.values.get("custom_canvas_api_domain")
    if canvas_domain not in ALLOWED_CANVAS_DOMAINS:
        msg = (
            "<p>This tool is only available from the following domain(s):<br/>{}</p>"
            "<p>You attempted to access from this domain:<br/>{}</p>"
        )
        return render_template(
            "error.htm.j2",
            message=msg.format(
                ", ".join(ALLOWED_CANVAS_DOMAINS), canvas_domain
            ),
        )

    course_id = request.form.get("custom_canvas_course_id")

    return redirect(url_for("show_assignments", course_id=course_id))


@app.route("/", methods=["GET"])
def index(lti=lti):
    return "Please contact your System Administrator."


@app.route("/status", methods=["GET"])
def status():
    """
    Runs smoke tests and reports status
    """
    status = {
        "tool": "Due Date Changer",
        "checks": {"index": False, "xml": False, "api_key": False},
        "url": url_for("index", _external=True),
        "xml_url": url_for("xml", _external=True),
        "canvas_url": CANVAS_URL,
        "debug": app.debug,
    }

    # Check index
    try:
        response = requests.get(url_for("index", _external=True), verify=False)
        status["checks"]["index"] = (
            response.text == "Please contact your System Administrator."
        )
    except Exception:
        app.logger.exception("Index check failed.")

    # Check xml
    try:
        response = requests.get(url_for("xml", _external=True), verify=False)
        status["checks"]["xml"] = "application/xml" in response.headers.get(
            "Content-Type"
        )
    except Exception:
        app.logger.exception("XML check failed.")

    # Check API Key
    try:
        self_user = canvas.get_user("self")
        status["checks"]["api_key"] = isinstance(self_user, User)
    except Exception:
        app.logger.exception("API check failed.")

    # Overall health check - if all checks are True
    status["healthy"] = all(v is True for k, v in status["checks"].items())

    return Response(json.dumps(status), mimetype="application/json")


@app.route("/course/<course_id>/assignments", methods=["GET"])
@lti(error=error, request="session", role="staff", app=app)
def show_assignments(course_id, lti=lti):
    try:
        course = canvas.get_course(course_id)
        assignments = course.get_assignments()
        quiz_dict = {quiz.id: quiz for quiz in course.get_quizzes()}
    except CanvasException as err:
        app.logger.exception(
            "Error getting course, assignments or quizzes from Canvas."
        )
        return error({"exception": err})

    assignment_quiz_list = []
    try:
        for assignment in assignments:
            if hasattr(assignment, "quiz_id"):
                quiz = quiz_dict.get(assignment.quiz_id)
                if hasattr(quiz, "show_correct_answers_at_date"):
                    assignment.show_correct_answers_at_date = datetime_localize(
                        quiz.show_correct_answers_at_date
                    )
                if hasattr(quiz, "hide_correct_answers_at_date"):
                    assignment.hide_correct_answers_at_date = datetime_localize(
                        quiz.hide_correct_answers_at_date
                    )
            assignment_quiz_list.append(assignment)
    except CanvasException as err:
        app.logger.exception("Error getting assignments from Canvas.")
        return error({"exception": err})

    return render_template(
        "assignments.htm.j2", assignments=assignment_quiz_list, course=course
    )


@app.route("/course/<course_id>/update", methods=["POST"])
@lti(error=error, request="session", role="staff", app=app)
def update_assignments(course_id, lti=lti):
    def fix_date(value):
        try:
            value = datetime.strptime(value, LOCAL_TIME_FORMAT)
            value = local_tz.localize(value)
            return value.isoformat()
        except (ValueError, TypeError):
            # Not a valid time. Just ignore.
            return ""

    def error_json(assignment_id, updated_list):
        msg = "There was an error editing one of the assignments. (ID: {})"
        msg = msg.format(assignment_id)
        if len(updated_list) > 0:
            "{} {} assignments have been updated successfully.".format(
                msg, len(updated_list)
            )

        return Response(
            json.dumps({"error": True, "message": msg, "updated": updated_list}),
            mimetype="application/json",
        )

    if not request.is_xhr:
        return render_template("error.htm.j2", message="Non-AJAX requests not allowed.")

    try:
        course = canvas.get_course(course_id)
    except CanvasException:
        msg = "Error getting course #{}.".format(course_id)
        app.logger.exception(msg)
        return Response(
            json.dumps({"error": True, "message": msg, "updated": []}),
            mimetype="application/json",
        )

    post_data = request.form

    local_tz = timezone(TIME_ZONE)
    assignment_field_map = defaultdict(dict)

    for key, value in six.iteritems(post_data):
        if not re.match(r"\d+-[a-z_]+", key):
            continue

        assignment_id, field_name = key.split("-")
        assignment_field_map[assignment_id].update({field_name: value})

    if len(assignment_field_map) < 1:
        return Response(
            json.dumps(
                {
                    "error": True,
                    "message": "There were no assignments to update.",
                    "updated": [],
                }
            ),
            mimetype="application/json",
        )

    updated_list = []
    for assignment_id, field in six.iteritems(assignment_field_map):
        assignment_type = field.get("assignment_type", "assignment")
        quiz_id = field.get("quiz_id")

        payload = {
            "published": field.get("published") == "on",
            "due_at": fix_date(field.get("due_at")),
            "lock_at": fix_date(field.get("lock_at")),
            "unlock_at": fix_date(field.get("unlock_at")),
        }

        if assignment_type == "quiz" and quiz_id:
            payload.update(
                {
                    "show_correct_answers_at": fix_date(
                        field.get("show_correct_answers_at")
                    ),
                    "hide_correct_answers_at": fix_date(
                        field.get("hide_correct_answers_at")
                    ),
                }
            )

            try:
                quiz = course.get_quiz(quiz_id)
                quiz.edit(quiz=payload)
                updated_list.append(
                    {"id": assignment_id, "title": quiz.title, "type": "Quiz"}
                )
            except CanvasException:
                app.logger.exception("Error getting/editing quiz #{}.".format(quiz_id))

                return error_json(assignment_id, updated_list)

        else:
            try:
                assignment = course.get_assignment(assignment_id)
                assignment.edit(assignment=payload)
                updated_list.append(
                    {
                        "id": assignment_id,
                        "title": assignment.name,
                        "type": "Assignment",
                    }
                )
            except CanvasException:
                app.logger.exception(
                    "Error getting/editing assignment #{}.".format(assignment_id)
                )

                return error_json(assignment_id, updated_list)

    return Response(
        json.dumps(
            {
                "error": False,
                "message": "Successfully updated {} assignments.".format(
                    len(updated_list)
                ),
                "updated": updated_list,
            }
        ),
        mimetype="application/json",
    )


@app.route("/lti.xml", methods=["GET"])
def xml():
    return Response(render_template("lti.xml.j2"), mimetype="application/xml")


@app.template_filter()
def datetime_localize(utc_datetime, format=LOCAL_TIME_FORMAT):
    if not utc_datetime.tzinfo:
        # Localize to UTC if there is no timezone information.
        utc_datetime = utc.localize(utc_datetime)

    new_tz = timezone(TIME_ZONE)
    local_datetime = utc_datetime.astimezone(new_tz)

    return local_datetime.strftime(format)
