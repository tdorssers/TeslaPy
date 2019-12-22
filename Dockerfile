FROM python:3.7-slim

ADD requirements.txt /
RUN pip install -r requirements.txt

COPY teslapy /teslapy/
COPY media /media/
COPY cli.py /
COPY menu.py /
COPY gui.py /
