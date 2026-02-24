FROM debian:bookworm-slim


ENV port=8030
ENV name="Panel"
ENV start_script=?
ENV stop_script=?

ENV DEBIAN_FRONTEND=noninteractive


RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    chromium \
    chromium-common \
    chromium-l10n \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-dejavu \
    libgtk-3-0 \
    libgbm1 \
    libgl1-mesa-dri \
    libasound2 \
    procps \
    wlr-randr \
    sway \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


RUN useradd -u 1000 -m -s /bin/bash pi
WORKDIR /home/pi/app


COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY . .

RUN chown -R pi:pi /home/pi/app
USER pi

ENV DISPLAY=:0

CMD ["sh", "-c", "python3 screen_webthing.py $port \"$name\" \"$start_script\" \"$stop_script\""]