# -*- coding: utf-8 -*-

from collections import defaultdict
import json
import logging
from logging.handlers import RotatingFileHandler
import re
from subprocess import call

import requests

from flask import Flask, redirect, render_template, request, url_for, Response
from canvasapi import Canvas
from canvasapi.user import User
from canvasapi.exceptions import CanvasException
from pylti.flask import lti
from pytz import utc, timezone
import redis
from redis.exceptions import ConnectionError
from rq import get_current_job, Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError

from utils import fix_date, update_job
import config

app = Flask(__name__)
app.config.from_object("config")

app.conn = redis.from_url(config.REDIS_URL)
app.q = Queue(config.RQ_WORKER, connection=app.conn)

formatter = logging.Formatter(config.LOG_FORMAT)
handler = RotatingFileHandler(
    config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUP_COUNT
)
handler.setLevel(logging.getLevelName(config.LOG_LEVEL))
handler.setFormatter(formatter)
app.logger.addHandler(handler)

canvas = Canvas(config.CANVAS_URL, config.API_KEY)


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
    if canvas_domain not in config.ALLOWED_CANVAS_DOMAINS:
        msg = (
            "<p>This tool is only available from the following domain(s):<br/>{}</p>"
            "<p>You attempted to access from this domain:<br/>{}</p>"
        )
        return render_template(
            "error.htm.j2",
            message=msg.format(", ".join(config.ALLOWED_CANVAS_DOMAINS), canvas_domain),
        )

    course_id = request.form.get("custom_canvas_course_id")

    return redirect(url_for("show_assignments", course_id=course_id))


@app.route("/", methods=["GET"])
def index(lti=lti):
    return "Please contact your System Administrator."


@app.route("/status", methods=["GET"])
def status():  # pragma:nocover
    """
    Runs smoke tests and reports status
    """
    status = {
        "tool": "Due Date Changer",
        "checks": {
            "index": False,
            "xml": False,
            "api_key": False,
            "redis": False,
            "worker": False,
        },
        "url": url_for("index", _external=True),
        "canvas_url": config.CANVAS_URL,
        "debug": app.debug,
        "xml_url": url_for("xml", _external=True),
        "job_queue": None,
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

    # Check redis
    try:
        response = app.conn.echo("test")
        status["checks"]["redis"] = response == b"test"
    except ConnectionError:
        app.logger.exception("Redis connection failed.")

    # Get redis queue length
    try:
        status["job_queue"] = len(app.q.jobs)
    except ConnectionError:
        app.logger.exception("Unable to get job queue length.")

    # Check RQ Worker
    status["checks"]["worker"] = (
        call('ps aux | grep "rq worker" | grep "ddc" | grep -v grep', shell=True) == 0
    )

    # Overall health check - if all checks are True
    checks_pass = all(v is True for k, v in status["checks"].items())
    queue_healthy = status["job_queue"] is not None

    status["healthy"] = checks_pass and queue_healthy

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


@app.route("/jobs/<job_key>/", methods=["GET"])
def job_status(job_key):
    try:
        job = Job.fetch(job_key, connection=app.conn)
    except NoSuchJobError:
        return Response(
            json.dumps(
                {
                    "error": True,
                    "status_msg": "{} is not a valid job key.".format(job_key),
                }
            ),
            mimetype="application/json",
            status=404,
        )

    if job.is_finished:
        return Response(json.dumps(job.result), mimetype="application/json", status=200)
    elif job.is_failed:
        app.logger.error("Job {} failed.\n{}".format(job_key, job.exc_info))
        return Response(
            json.dumps(
                {
                    "error": True,
                    "status_msg": "Job {} failed to complete.".format(job_key),
                }
            ),
            mimetype="application/json",
            status=500,
        )
    else:
        return Response(json.dumps(job.meta), mimetype="application/json", status=202)


def update_assignments_background(course_id, post_data):
    """
    Update all assignments in a course.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    """
    job = get_current_job()

    update_job(job, 0, "Starting...", "started")

    try:
        course = canvas.get_course(course_id)
    except CanvasException:
        msg = "Error getting course #{}.".format(course_id)
        app.logger.exception(msg)
        update_job(job, 0, msg, "failed", error=True)
        return job.meta

    assignment_field_map = defaultdict(dict)

    for key, value in post_data.items():
        if not re.match(r"\d+-[a-z_]+", key):
            continue

        assignment_id, field_name = key.split("-")
        assignment_field_map[assignment_id].update({field_name: value})

    num_assignments = len(assignment_field_map)

    if num_assignments < 1:
        update_job(job, 0, "There were no assignments to update.", "failed", error=True)
        return job.meta

    updated_list = []
    for index, (assignment_id, field) in enumerate(assignment_field_map.items(), 1):
        assignment_type = field.get("assignment_type", "assignment")
        quiz_id = field.get("quiz_id")

        payload = {
            "published": field.get("published") == "on",
            "due_at": fix_date(field.get("due_at")),
            "lock_at": fix_date(field.get("lock_at")),
            "unlock_at": fix_date(field.get("unlock_at")),
        }

        comp_perc = int((index / num_assignments) * 100)
        msg = "Updating Assignment #{} [{} of {}]"
        update_job(
            job,
            comp_perc,
            msg.format(assignment_id, index, num_assignments),
            "processing",
            error=False,
        )

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
                msg = "Error getting/editing quiz #{}.".format(quiz_id)

                app.logger.exception(msg)
                update_job(job, comp_perc, msg, "failed", error=True)

                return job.meta

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
                msg = "Error getting/editing assignment #{}.".format(assignment_id)

                app.logger.exception(msg)
                update_job(job, comp_perc, msg, "failed", error=True)

                return job.meta

    msg = "Successfully updated {} assignments.".format(len(updated_list))
    update_job(job, 100, msg, "complete", error=False)
    job.meta["updated_list"] = updated_list
    job.save()

    return job.meta


@app.route("/course/<course_id>/update", methods=["POST"])
@lti(error=error, request="session", role="staff", app=app)
def update_assignments(course_id, lti=lti):
    """
    Creates a new `update_assignments_background` job.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int

    :rtype: flask.Response
    :returns: A JSON-formatted response containing a URL for the started job.
    """

    job = app.q.enqueue_call(
        func=update_assignments_background, args=(course_id, request.form)
    )
    update_job(job, 0, "Job Queued.", "queued")
    return Response(
        json.dumps(
            {"update_assignments_job_url": url_for("job_status", job_key=job.get_id())}
        ),
        mimetype="application/json",
        status=202,
    )


@app.route("/lti.xml", methods=["GET"])
def xml():
    return Response(
        render_template("lti.xml.j2", course_nav_disabled=config.DISABLE_COURSE_NAV),
        mimetype="application/xml",
    )


@app.template_filter()
def datetime_localize(utc_datetime, format=config.LOCAL_TIME_FORMAT):
    if not utc_datetime.tzinfo:
        # Localize to UTC if there is no timezone information.
        utc_datetime = utc.localize(utc_datetime)

    new_tz = timezone(config.TIME_ZONE)
    local_datetime = utc_datetime.astimezone(new_tz)

    return local_datetime.strftime(format)


@app.template_test("quiz")
def is_quiz(assignment):
    return "online_quiz" in getattr(assignment, "submission_types", {})


@app.template_test("discussion")
def is_discussion(assignment):
    return "discussion_topic" in getattr(assignment, "submission_types", {})
