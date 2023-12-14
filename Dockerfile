FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

ADD main.py .

CMD ["python3", "-u", "./main.py"]
