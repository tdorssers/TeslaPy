FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends tk chromium-driver \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*

ADD requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY teslapy /app/teslapy/
COPY cli.py /app
COPY menu.py /app
COPY gui.py /app

COPY entrypoint.sh /app

WORKDIR /home/tsla
RUN useradd tsla && chown tsla:tsla /home/tsla
USER tsla

ENV DISPLAY=:0

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["help"]
