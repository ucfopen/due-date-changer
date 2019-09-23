# -*- coding: utf-8 -*-

import re

from datetime import datetime
import logging
import oauthlib.oauth1
from urllib.parse import urlencode
import unittest
from unittest.mock import patch

from fakeredis import FakeStrictRedis
import flask_testing
from pylti.common import LTI_SESSION_KEY
from pytz import timezone
import requests_mock
from rq import Queue


@patch("config.ALLOWED_CANVAS_DOMAINS", ["example.edu"])
@requests_mock.Mocker()
class LTITests(flask_testing.TestCase):
    @patch("redis.from_url", FakeStrictRedis)
    def create_app(self):
        import lti

        app = lti.app
        app.config["PRESERVE_CONTEXT_ON_EXCEPTION"] = False
        app.config["API_URL"] = "http://example.edu/api/v1/"
        app.config["API_KEY"] = "p@$$w0rd"
        return app

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    # index()
    def test_index(self, m):
        response = self.client.get(self.generate_launch_request("/"))

        self.assert_200(response)
        self.assertEqual(response.data, b"Please contact your System Administrator.")

    # xml()
    def test_xml(self, m):
        response = self.client.get("/lti.xml")
        self.assert_200(response)
        self.assert_template_used("lti.xml.j2")
        self.assertIn("application/xml", response.content_type)

    # launch()
    def test_launch(self, m):
        payload = {
            "custom_canvas_course_id": "1",
            "custom_canvas_api_domain": "example.edu",
        }

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            body=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload)

        self.assertRedirects(response, "/course/1/assignments")

    def test_launch_wrong_domain(self, m):
        payload = {
            "custom_canvas_course_id": "1",
            "custom_canvas_api_domain": "example.com",
        }

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            body=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload)

        self.assert_200(response)
        self.assert_template_used("error.htm.j2")

    def test_launch_no_domain(self, m):
        payload = {"custom_canvas_course_id": "1"}

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            body=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload)

        # import pdb; pdb.set_trace()
        self.assert_200(response)
        self.assert_template_used("error.htm.j2")

    # show_assignments()
    def test_show_assignments_role_student(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Student"

        response = self.client.get(
            self.generate_launch_request("/course/1/assignments")
        )
        self.assert_200(response)
        self.assert_template_used("error.htm.j2")
        self.assertEqual(str(self.get_context_variable("message")), "Not authorized.")

    def test_show_assignments_course_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Instructor"

        m.register_uri(
            "GET",
            "/api/v1/courses/1",
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234,
            },
            status_code=404,
        )

        response = self.client.get(
            self.generate_launch_request("/course/1/assignments")
        )
        self.assert_200(response)
        self.assert_template_used("error.htm.j2")
        self.assertEqual(str(self.get_context_variable("message")), "Not Found")

    def test_show_assignments_quizzes_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Instructor"

        m.register_uri(
            "GET",
            "/api/v1/courses/1",
            json={"id": 1, "name": "Course 1"},
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234,
            },
            status_code=404,
        )

        response = self.client.get(
            self.generate_launch_request("/course/1/assignments")
        )
        self.assert_200(response)
        self.assert_template_used("error.htm.j2")
        self.assertEqual(str(self.get_context_variable("message")), "Not Found")

    def test_show_assignments_assignments_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Instructor"

        m.register_uri(
            "GET",
            "/api/v1/courses/1",
            json={"id": 1, "name": "Course 1"},
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[{"id": 1, "title": "Quiz 1"}, {"id": 2, "title": "Quiz 2"}],
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/assignments",
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234,
            },
            status_code=404,
        )

        response = self.client.get(
            self.generate_launch_request("/course/1/assignments")
        )
        self.assert_200(response)
        self.assert_template_used("error.htm.j2")
        self.assertEqual(str(self.get_context_variable("message")), "Not Found")

    def test_show_assignments(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Instructor"

        m.register_uri(
            "GET",
            "/api/v1/courses/1",
            json={"id": 1, "name": "Course 1"},
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {
                    "id": 1,
                    "title": "Quiz 1",
                    "show_correct_answers_at": "2017-01-13T00:00:01Z",
                    "hide_correct_answers_at": "2017-12-31T23:59:59Z",
                },
                {"id": 2, "title": "Quiz 2"},
            ],
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/assignments",
            json=[
                {"id": 1, "title": "Non-Quiz Assignment 1"},
                {"id": 2, "title": "Quiz 1", "quiz_id": 1},
                {"id": 3, "title": "Quiz 2", "quiz_id": 2},
                {"id": 4, "title": "Non- Quiz Assignment 2"},
            ],
            status_code=200,
        )

        response = self.client.get(
            self.generate_launch_request("/course/1/assignments")
        )
        self.assert_200(response)
        self.assert_template_used("assignments.htm.j2")
        assignments = self.get_context_variable("assignments")
        self.assertIsInstance(assignments, list)
        self.assertEqual(len(assignments), 4)

    # update_assignments()
    def test_update_assignments(self, m):
        from rq.job import Job

        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "Instructor"

        payload = {"42-assignment_type": "assignment", "42-published": False}
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = self.client.post(
            self.generate_launch_request(
                "/course/1/update",
                http_method="POST",
                body=urlencode(payload),
                headers=headers,
            ),
            data=payload,
            headers=headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertTrue(hasattr(response, "json"))
        self.assertIsInstance(response.json, dict)
        self.assertIn("update_assignments_job_url", response.json)
        self.assertIn("/jobs/", response.json["update_assignments_job_url"])

        id_pat = r"[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}"
        job_id = re.search(id_pat, response.json["update_assignments_job_url"])[0]

        job = Job.fetch(job_id, connection=self.app.conn)

        self.assertIsInstance(job, Job)
        self.assertTrue(hasattr(job, "meta"))
        self.assertIsInstance(job.meta, dict)
        self.assertIn("status", job.meta)
        self.assertEqual(job.meta["status"], "queued")

    # job_status()
    def test_job_status_no_such_job(self, m):
        response = self.client.get("/jobs/fakejob/")

        self.assertEqual(response.status_code, 404)

        self.assertTrue(hasattr(response, "json"))
        self.assertIsInstance(response.json, dict)
        self.assertIn("error", response.json)
        self.assertTrue(response.json["error"])

        self.assertIn("status_msg", response.json)
        self.assertEqual(response.json["status_msg"], "fakejob is not a valid job key.")

    def test_job_status_finished(self, m):
        def test_func():
            pass  # pragma: nocover

        job = self.app.q.enqueue_call(test_func)
        job.set_status("finished")
        job._result = {"status": "done"}
        job.save()
        response = self.client.get(f"/jobs/{job.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "done"})

    def test_job_status_failed(self, m):
        def test_func():
            pass  # pragma: nocover

        job = self.app.q.enqueue_call(test_func)
        job.set_status("failed")
        response = self.client.get(f"/jobs/{job.id}/")

        self.assertEqual(response.status_code, 500)

        self.assertTrue(hasattr(response, "json"))
        self.assertIsInstance(response.json, dict)
        self.assertIn("error", response.json)
        self.assertTrue(response.json["error"])

        self.assertIn("status_msg", response.json)
        self.assertEqual(
            response.json["status_msg"], f"Job {job.id} failed to complete."
        )

    def test_job_status(self, m):
        def test_func():
            pass  # pragma: nocover

        job = self.app.q.enqueue_call(test_func)
        job.meta = {"status": "accepted"}
        job.save()
        response = self.client.get(f"/jobs/{job.id}/")

        self.assertEqual(response.status_code, 202)

        self.assertTrue(hasattr(response, "json"))
        self.assertIsInstance(response.json, dict)
        self.assertIn("status", response.json)
        self.assertEqual(response.json["status"], "accepted")

    # update_assignments_background
    def test_update_assignments_background_invalid_course(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", status_code=404)

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(func=update_assignments_background, args=(1, {}))
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "failed")
        self.assertIn("status_msg", job.result)
        self.assertEqual(job.result["status_msg"], "Error getting course #1.")
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 0)
        self.assertIn("error", job.result)
        self.assertTrue(job.result["error"])

    def test_update_assignments_background_no_assignments(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(func=update_assignments_background, args=(1, {}))
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "failed")
        self.assertIn("status_msg", job.result)
        self.assertEqual(
            job.result["status_msg"], "There were no assignments to update."
        )
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 0)
        self.assertIn("error", job.result)
        self.assertTrue(job.result["error"])

    def test_update_assignments_background_invalid_data(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(
            func=update_assignments_background, args=(1, {"key": "value"})
        )
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "failed")
        self.assertIn("status_msg", job.result)
        self.assertEqual(
            job.result["status_msg"], "There were no assignments to update."
        )
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 0)
        self.assertIn("error", job.result)
        self.assertTrue(job.result["error"])

    def test_update_assignments_background_quiz(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes/5",
            json={"id": 5, "title": "Quiz 1"},
            status_code=200,
        )
        m.register_uri(
            "PUT",
            "/api/v1/courses/1/quizzes/5",
            json={"id": 5, "title": "Quiz 1", "due_at": "2020-01-13T10:00:00-05:00"},
            status_code=200,
        )

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(
            func=update_assignments_background,
            args=(
                1,
                {
                    "10-due_at": "01/13/2020 10:00 AM",
                    "10-assignment_type": "quiz",
                    "10-quiz_id": 5,
                },
            ),
        )
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "complete")
        self.assertIn("status_msg", job.result)
        self.assertEqual(
            job.result["status_msg"], "Successfully updated 1 assignments."
        )
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 100)
        self.assertIn("error", job.result)
        self.assertFalse(job.result["error"])

    def test_update_assignments_background_quiz_fail(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)
        m.register_uri("GET", "/api/v1/courses/1/quizzes/5", status_code=404)

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(
            func=update_assignments_background,
            args=(
                1,
                {
                    "10-due_at": "01/13/2020 10:00 AM",
                    "10-assignment_type": "quiz",
                    "10-quiz_id": 5,
                },
            ),
        )
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "failed")
        self.assertIn("status_msg", job.result)
        self.assertEqual(job.result["status_msg"], "Error getting/editing quiz #5.")
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 100)
        self.assertIn("error", job.result)
        self.assertTrue(job.result["error"])

    def test_update_assignments_background_assignment(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)
        m.register_uri(
            "GET",
            "/api/v1/courses/1/assignments/11",
            json={"id": 11, "name": "Assignment 1", "course_id": 1},
            status_code=200,
        )
        m.register_uri(
            "PUT",
            "/api/v1/courses/1/assignments/11",
            json={
                "id": 11,
                "name": "Assignment 1",
                "due_at": "2020-01-13T10:00:00-05:00",
                "course_id": 1,
            },
            status_code=200,
        )

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(
            func=update_assignments_background,
            args=(
                1,
                {
                    "11-due_at": "01/13/2020 11:00 AM",
                    "11-assignment_type": "assignment",
                },
            ),
        )
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "complete")
        self.assertIn("status_msg", job.result)
        self.assertEqual(
            job.result["status_msg"], "Successfully updated 1 assignments."
        )
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 100)
        self.assertIn("error", job.result)
        self.assertFalse(job.result["error"])

    def test_update_assignments_background_assignment_fail(self, m):
        from lti import update_assignments_background

        m.register_uri("GET", "/api/v1/courses/1", json={"id": 1}, status_code=200)
        m.register_uri("GET", "/api/v1/courses/1/assignments/11", status_code=404)

        queue = Queue(is_async=False, connection=FakeStrictRedis())
        job = queue.enqueue_call(
            func=update_assignments_background,
            args=(
                1,
                {
                    "11-due_at": "01/13/2020 11:00 AM",
                    "11-assignment_type": "assignment",
                },
            ),
        )
        self.assertTrue(job.is_finished)

        self.assertTrue(hasattr(job, "result"))
        self.assertIsInstance(job.result, dict)
        self.assertIn("status", job.result)
        self.assertEqual(job.result["status"], "failed")
        self.assertIn("status_msg", job.result)
        self.assertEqual(
            job.result["status_msg"], "Error getting/editing assignment #11."
        )
        self.assertIn("percent", job.result)
        self.assertEqual(job.result["percent"], 100)
        self.assertIn("error", job.result)
        self.assertTrue(job.result["error"])

    # datetime_localize()
    @patch("config.TIME_ZONE", "US/Eastern")
    def test_datetime_localize(self, m):
        # TODO: this test may be sensitive to Daylight Saving Time and
        # other such nonsense. Investigate workarounds.
        from lti import datetime_localize

        utc_time = datetime(2020, 1, 13, 11, tzinfo=timezone("US/Eastern"))
        local_time = "01/13/2020 11:00 AM"

        localized = datetime_localize(utc_time)

        self.assertIsInstance(localized, str)
        self.assertEqual(localized, local_time)

    @patch("config.TIME_ZONE", "US/Eastern")
    def test_datetime_localize_no_tz(self, m):
        from lti import datetime_localize

        utc_time = datetime(2020, 1, 13, 11)
        local_time = "01/13/2020 06:00 AM"

        localized = datetime_localize(utc_time)

        self.assertIsInstance(localized, str)
        self.assertEqual(localized, local_time)

    @staticmethod
    def generate_launch_request(
        url,
        body=None,
        http_method="GET",
        base_url="http://localhost",
        roles="Instructor",
        headers=None,
    ):

        params = {}

        if roles is not None:
            params["roles"] = roles

        urlparams = urlencode(params)

        client = oauthlib.oauth1.Client(
            "key",
            client_secret="secret",
            signature_method=oauthlib.oauth1.SIGNATURE_HMAC,
            signature_type=oauthlib.oauth1.SIGNATURE_TYPE_QUERY,
        )
        signature = client.sign(
            "{}{}?{}".format(base_url, url, urlparams),
            body=body,
            http_method=http_method,
            headers=headers,
        )
        signed_url = signature[0]
        new_url = signed_url[len(base_url) :]
        return new_url


class UtilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    # fix_date()
    def test_fix_date(self):
        # TODO: this test may be sensitive to Daylight Saving Time and
        # other such nonsense. Investigate workarounds.
        from lti import fix_date

        response = fix_date("01/13/2020 11:00 AM")
        self.assertIsInstance(response, str)
        self.assertEqual(response, "2020-01-13T11:00:00-05:00")

    def test_fix_date_invalid(self):
        # TODO: this test may be sensitive to Daylight Saving Time and
        # other such nonsense. Investigate workarounds.
        from lti import fix_date

        response = fix_date("01/13/2020 13:00 AM")
        self.assertIsInstance(response, str)
        self.assertEqual(response, "")

    # update_job()
    def test_update_job(self):
        from lti import update_job

        def fake_job():
            pass  # pragma:nocover

        queue = Queue(connection=FakeStrictRedis())
        job = queue.enqueue_call(func=fake_job, args=(1, {}))

        self.assertIsInstance(job.meta, dict)
        self.assertEqual(len(job.meta), 0)

        update_job(job, 42, "This is the status", "status_code")

        self.assertEqual(len(job.meta), 4)

        self.assertIn("percent", job.meta)
        self.assertEqual(job.meta["percent"], 42)
        self.assertIn("status", job.meta)
        self.assertEqual(job.meta["status"], "status_code")
        self.assertIn("status_msg", job.meta)
        self.assertEqual(job.meta["status_msg"], "This is the status")
        self.assertIn("error", job.meta)
        self.assertFalse(job.meta["error"])
