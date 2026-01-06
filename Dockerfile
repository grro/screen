FROM python:3-alpine

ENV port 8031
ENV name ?

RUN apt-get update && apt-get install -y wlr-randr && rm -rf /var/lib/apt/lists/*

RUN cd /etc
RUN mkdir app
WORKDIR /etc/app
ADD *.py /etc/app/
ADD requirements.txt /etc/app/.
RUN pip install -r requirements.txt

CMD python /etc/app/server.py $port $name



