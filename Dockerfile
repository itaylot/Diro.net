# מצאן — all-in-one image (Chromium baked in for Selenium)
FROM python:3.12-slim

# Chromium + driver + the libs Selenium needs to render Facebook/Yad2
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    fonts-liberation libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 \
    libasound2 ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Let Selenium find the system Chromium
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    TZ=Asia/Jerusalem \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5050

# The supervisor runs the dashboard + bot + both scanners and keeps them alive.
CMD ["python", "run_all.py"]
