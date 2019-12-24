FROM python:3.7-slim

ADD requirements.txt /

RUN apt-get update && apt-get install -y --no-install-recommends tk \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements.txt

COPY teslapy /teslapy/
COPY cli.py /
COPY menu.py /
COPY gui.py /

COPY entrypoint.sh /

ENV DISPLAY=172.16.247.1:0.0

ENTRYPOINT ["/entrypoint.sh"]
CMD ["help"]

