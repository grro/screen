FROM python:3-alpine

ENV port 8031
ENV name ?

RUN apk update && apk add --no-cache wlr-randr

RUN cd /etc
RUN mkdir app
WORKDIR /etc/app
ADD *.py /etc/app/
ADD requirements.txt /etc/app/.
RUN pip install -r requirements.txt

CMD python /etc/app/screen_webthing.py $port $name



