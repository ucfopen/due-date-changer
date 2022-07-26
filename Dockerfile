FROM python:3.7
ARG REQUIREMENTS

COPY ./requirements.txt /code/requirements.txt
COPY ./test_requirements.txt /code/test_requirements.txt

RUN pip install --upgrade pip
RUN pip install -r /code/$REQUIREMENTS

WORKDIR /code
COPY ./ /code/
EXPOSE 3109
CMD ["gunicorn", "--conf", "gunicorn_conf.py", "--bind", "0.0.0.0:3109", "lti:app"]
