from urllib import urlencode
import oauthlib.oauth1
import logging

import flask_testing
import requests_mock
from pylti.common import LTI_SESSION_KEY

import lti


@requests_mock.Mocker()
class LTITests(flask_testing.TestCase):

    def create_app(self):
        app = lti.app
        app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False
        app.config['API_URL'] = 'http://example.edu/api/v1/'
        app.config['API_KEY'] = 'p@$$w0rd'
        return app

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    def test_index(self, m):
        response = self.client.get(self.generate_launch_request('/'))

        self.assert_200(response)
        self.assertEqual(
            response.data,
            'Please contact your System Administrator.'
        )

    def test_xml(self, m):
        response = self.client.get('/lti.xml')

        self.assert_200(response)
        self.assert_template_used('lti.xml.j2')
        self.assertIn('application/xml', response.content_type)

    def test_launch(self, m):
        payload = {'custom_canvas_course_id': '1'}

        signed_url = self.generate_launch_request(
            '/launch',
            http_method="POST",
            body=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        response = self.client.post(
            signed_url,
            data=payload,
        )

        self.assertRedirects(response, '/course/1/assignments')

    def test_show_assignments_role_student(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Student'

        response = self.client.get(
            self.generate_launch_request('/course/1/assignments')
        )
        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            str(self.get_context_variable('message')),
            'Not authorized.'
        )

    def test_show_assignments_course_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234
            },
            status_code=404
        )

        response = self.client.get(
            self.generate_launch_request('/course/1/assignments')
        )
        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            str(self.get_context_variable('message')),
            'Not Found'
        )

    def test_show_assignments_quizzes_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/quizzes',
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234
            },
            status_code=404
        )

        response = self.client.get(
            self.generate_launch_request('/course/1/assignments')
        )
        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            str(self.get_context_variable('message')),
            'Not Found'
        )

    def test_show_assignments_assignments_not_found(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/quizzes',
            json=[
                {
                    'id': 1,
                    'title': 'Quiz 1'
                },
                {
                    'id': 2,
                    'title': 'Quiz 2'
                }
            ],
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments',
            json={
                "errors": [{"message": "The specified resource does not exist."}],
                "error_report_id": 1234
            },
            status_code=404
        )

        response = self.client.get(
            self.generate_launch_request('/course/1/assignments')
        )
        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            str(self.get_context_variable('message')),
            'Not Found'
        )

    def test_show_assignments(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/quizzes',
            json=[
                {
                    'id': 1,
                    'title': 'Quiz 1',
                    'show_correct_answers_at': '2017-01-01T00:00:01Z',
                    'hide_correct_answers_at': '2017-12-31T23:59:59Z'
                },
                {
                    'id': 2,
                    'title': 'Quiz 2',
                }
            ],
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments',
            json=[
                {
                    'id': 1,
                    'title': 'Non-Quiz Assignment 1'
                },
                {
                    'id': 2,
                    'title': 'Quiz 1',
                    'quiz_id': 1
                },
                {
                    'id': 3,
                    'title': 'Quiz 2',
                    'quiz_id': 2
                },
                {
                    'id': 4,
                    'title': 'Non- Quiz Assignment 2'
                }
            ],
            status_code=200
        )

        response = self.client.get(
            self.generate_launch_request('/course/1/assignments')
        )
        self.assert_200(response)
        self.assert_template_used('assignments.htm.j2')
        assignments = self.get_context_variable('assignments')
        self.assertIsInstance(assignments, list)
        self.assertEqual(len(assignments), 4)

    def test_update_assignments_role_student(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Student'

        response = self.client.post(
            self.generate_launch_request('/course/1/update', http_method='POST')
        )

        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            str(self.get_context_variable('message')),
            'Not authorized.'
        )

    def test_update_assignments_no_xhr(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        response = self.client.post(
            self.generate_launch_request('/course/1/update', http_method='POST')
        )

        self.assert_200(response)
        self.assert_template_used('error.htm.j2')
        self.assertEqual(
            self.get_context_variable('message'),
            'Non-AJAX requests not allowed.'
        )

    def test_update_assignments_invalid_data(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )

        payload = {'key': 'value'}
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )
        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertTrue(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'There were no assignments to update.'
        )
        self.assertEqual(len(response.json['updated']), 0)

    def test_update_assignments_invalid_course(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            status_code=404
        )

        payload = {'key': 'value'}
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )

        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertTrue(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'Error getting course #1.'
        )
        self.assertEqual(len(response.json['updated']), 0)

    def test_update_assignments_edit_assignment_error(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        ),
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/42',
            status_code=404
        )

        payload = {
            '42-assignment_type': 'assignment',
            '42-published': False
        }
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )

        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertTrue(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'There was an error editing one of the assignments. (ID: 42)'
        )
        self.assertEqual(len(response.json['updated']), 0)

    def test_update_assignments_no_quiz(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        ),
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        )

        payload = {
            '42-assignment_type': 'assignment',
            '42-published': False
        }
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )

        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertFalse(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'Successfully updated 1 assignments.'
        )
        self.assertEqual(len(response.json['updated']), 1)

    def test_update_assignments_missing_quiz(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        ),
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/10',
            json={
                'id': 10,
                'name': 'Quiz Assignment',
                'course_id': 1,
                'quiz_id': 55,
            },
            status_code=200
        ),
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        )
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/10',
            json={
                'id': 10,
                'name': 'Quiz Assignment',
                'course_id': 1,
                'quiz_id': 55
            },
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/quizzes/55',
            json={
                'id': 55,
                'title': 'Quiz Assignment',
                'course_id': 1,
            },
            status_code=404
        )

        payload = {
            '42-assignment_type': 'assignment',
            '42-published': 'on',
            '10-assignment_type': 'quiz',
            '10-quiz_id': 55,
            '10-published': 'on',
            '10-due_at': '01/01/2017 10:00 AM'
        }
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )

        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertTrue(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'There was an error editing one of the assignments. (ID: 10)'
        )
        self.assertEqual(len(response.json['updated']), 0)

    def test_update_assignments_working_quiz(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess['oauth_consumer_key'] = 'key'
            sess['roles'] = 'Instructor'

        m.register_uri(
            'GET',
            '/api/v1/courses/1',
            json={'id': 1, 'name': 'Course 1'},
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        ),
        m.register_uri(
            'GET',
            '/api/v1/courses/1/assignments/10',
            json={
                'id': 10,
                'name': 'Quiz Assignment',
                'course_id': 1,
                'quiz_id': 55,
            },
            status_code=200
        ),
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/42',
            json={
                'id': 42,
                'name': 'The Answer',
                'course_id': 1
            },
            status_code=200
        )
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/assignments/10',
            json={
                'id': 10,
                'name': 'Quiz Assignment',
                'course_id': 1,
                'quiz_id': 55
            },
            status_code=200
        )
        m.register_uri(
            'GET',
            '/api/v1/courses/1/quizzes/55',
            json={
                'id': 55,
                'title': 'Quiz Assignment',
                'course_id': 1,
            },
            status_code=200
        )
        m.register_uri(
            'PUT',
            '/api/v1/courses/1/quizzes/55',
            json={
                'id': 55,
                'title': 'Quiz Assignment',
                'course_id': 1,
            },
            status_code=200
        )

        payload = {
            '42-assignment_type': 'assignment',
            '42-published': 'on',
            '10-assignment_type': 'quiz',
            '10-quiz_id': 55,
            '10-published': 'on',
            '10-due_at': '01/01/2017 10:00 AM'
        }
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = self.client.post(
            self.generate_launch_request(
                '/course/1/update',
                http_method='POST',
                body=urlencode(payload),
                headers=headers
            ),
            data=payload,
            headers=headers
        )

        self.assert_200(response)
        self.assertIn('application/json', response.content_type)
        self.assertTrue(hasattr(response, 'json'))
        self.assertIsInstance(response.json, dict)
        self.assertFalse(response.json['error'])
        self.assertEqual(
            response.json['message'],
            'Successfully updated 2 assignments.'
        )
        self.assertEqual(len(response.json['updated']), 2)

    @staticmethod
    def generate_launch_request(
            url, body=None, http_method="GET", base_url='http://localhost',
            roles='Instructor', headers=None):

        params = {}

        if roles is not None:
            params['roles'] = roles

        urlparams = urlencode(params)

        client = oauthlib.oauth1.Client(
            'key',
            client_secret='secret',
            signature_method=oauthlib.oauth1.SIGNATURE_HMAC,
            signature_type=oauthlib.oauth1.SIGNATURE_TYPE_QUERY
        )
        signature = client.sign(
            "{}{}?{}".format(base_url, url, urlparams),
            body=body,
            http_method=http_method,
            headers=headers
        )
        signed_url = signature[0]
        new_url = signed_url[len(base_url):]
        return new_url
