FROM python:3-alpine

# Fix: ENV mit "=" nutzen, um Warnungen zu vermeiden
ENV port=8030
ENV name="Panel"
ENV start_script=?
ENV stop_script=?

# Korrigierte Pakete für Alpine:
# mesa-dri-gallium enthält die Software-Treiber (swrast)
# Wir entfernen den Intel-Treiber, da er auf dem Pi nicht funktioniert
RUN apk update && apk add --no-cache \
    wlr-randr \
    bash \
    chromium \
    font-noto \
    mesa-dri-gallium \
    mesa-gbm \
    udev \
    dbus

RUN mkdir -p /etc/app
WORKDIR /etc/app

# Kopieren der Dateien
COPY requirements.txt /etc/app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /etc/app/

# Fix: CMD im JSON-Format, um Signal-Probleme zu vermeiden
# Wir nutzen "sh -c", damit die Umgebungsvariablen korrekt aufgelöst werden
CMD ["sh", "-c", "python /etc/app/screen_webthing.py $port \"$name\" \"$start_script\" \"$stop_script\""]