import json
import sys
import threading
import time
from collections import deque
from html import escape

import paho.mqtt.client as mqtt
import serial
from flask import Flask, Response, jsonify, render_template_string


BAUD_RATE = 9600
MQTT_BROKER = "157.173.101.159"
MQTT_PORT = 1883
MQTT_TOPIC = "dht11/temperature"
MQTT_TOPIC_HUM = "dht11/humidity"
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 9272

DEFAULT_SERIAL_PORTS = [
    "/dev/ttyUSB0",
    "/dev/ttyACM0",
    "/dev/ttyUSB1",
    "/dev/ttyACM1",
]

app = Flask(__name__)
state_lock = threading.Lock()
history = deque(maxlen=80)
state = {
    "temperature": None,
    "humidity": None,
    "serial_port": None,
    "serial_status": "Waiting for Arduino serial port",
    "mqtt_status": "Connecting",
    "last_line": "",
    "last_update": None,
    "messages": 0,
}


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def update_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def snapshot():
    with state_lock:
        data = dict(state)
        data["history"] = list(history)
    return data


def on_connect(client, userdata, flags, rc, *extra):
    if rc == 0:
        update_state(mqtt_status=f"Connected to {MQTT_BROKER}:{MQTT_PORT}")
        print("[MQTT] Connected to broker")
    else:
        update_state(mqtt_status=f"Connection failed rc={rc}")
        print(f"[MQTT] Connection failed rc={rc}")


def on_disconnect(client, userdata, rc, *extra):
    if rc != 0:
        update_state(mqtt_status="Disconnected, retrying")
        print("[MQTT] Disconnected, retrying")


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect


def mqtt_worker():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_forever(retry_first_connection=True)
        except Exception as exc:
            update_state(mqtt_status=f"Unavailable: {exc}")
            print(f"[MQTT] Unavailable: {exc}")
            time.sleep(5)


def parse_reading(line):
    if not line.startswith("T:") or ",H:" not in line:
        return None

    parts = line.split(",", 1)
    temp = float(parts[0].replace("T:", ""))
    hum = float(parts[1].replace("H:", ""))
    return temp, hum


def publish_reading(temp, hum):
    mqtt_client.publish(MQTT_TOPIC, f"{temp:.1f}")
    mqtt_client.publish(MQTT_TOPIC_HUM, f"{hum:.1f}")


def serial_ports():
    if len(sys.argv) > 1:
        return [sys.argv[1]]
    return DEFAULT_SERIAL_PORTS


def serial_worker():
    ports = serial_ports()

    while True:
        for port in ports:
            try:
                print(f"[SERIAL] Opening {port} @ {BAUD_RATE}")
                update_state(serial_port=port, serial_status=f"Opening {port}")
                with serial.Serial(port, BAUD_RATE, timeout=1) as ser:
                    time.sleep(2)
                    update_state(serial_port=port, serial_status="Connected")
                    print(f"[SERIAL] Connected on {port}")

                    while True:
                        line = ser.readline().decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue

                        try:
                            reading = parse_reading(line)
                        except ValueError:
                            reading = None

                        if reading is None:
                            update_state(last_line=line)
                            print(f"[RAW] {line}")
                            continue

                        temp, hum = reading
                        timestamp = now_text()
                        publish_reading(temp, hum)

                        with state_lock:
                            state["temperature"] = temp
                            state["humidity"] = hum
                            state["last_line"] = line
                            state["last_update"] = timestamp
                            state["messages"] += 1
                            history.append(
                                {
                                    "time": timestamp,
                                    "temperature": temp,
                                    "humidity": hum,
                                }
                            )

                        print(f"[{timestamp}] Temp: {temp:.1f} C | Humidity: {hum:.1f} %")
            except serial.SerialException as exc:
                update_state(serial_port=port, serial_status=f"Not available: {exc}")
            except Exception as exc:
                update_state(serial_port=port, serial_status=f"Error: {exc}")
                print(f"[SERIAL] Error on {port}: {exc}")

        time.sleep(3)


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DHT11 Temperature Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, Helvetica, sans-serif;
      --ink: #172026;
      --muted: #607080;
      --panel: #ffffff;
      --line: #d9e2e7;
      --bg: #eef3f5;
      --accent: #0f766e;
      --warn: #b45309;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      padding: 22px 28px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.2;
    }
    .candidate {
      color: var(--muted);
      font-size: 14px;
      margin-top: 4px;
    }
    main {
      width: min(1120px, calc(100% - 32px));
      margin: 24px auto;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }
    .value {
      font-size: 36px;
      font-weight: 700;
      line-height: 1;
    }
    .unit {
      font-size: 18px;
      color: var(--muted);
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e6f4f1;
      color: #075e57;
      font-size: 13px;
      font-weight: 700;
    }
    .wide {
      margin-top: 14px;
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 14px;
    }
    canvas {
      width: 100%;
      height: 320px;
      display: block;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }
    th { color: var(--muted); font-weight: 700; }
    .meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }
    .meta .panel { padding: 14px; }
    .small {
      font-size: 14px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    @media (max-width: 820px) {
      .grid, .wide, .meta { grid-template-columns: 1fr; }
      header { padding: 18px 16px; }
      main { width: min(100% - 20px, 1120px); margin-top: 14px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>DHT11 Temperature Dashboard</h1>
      <div class="candidate">Candidate: UHIRIWE Chrisostom</div>
    </div>
    <div class="status" id="liveStatus">Waiting for data</div>
  </header>

  <main>
    <section class="grid">
      <div class="panel">
        <div class="label">Temperature</div>
        <div class="value"><span id="temperature">--</span> <span class="unit">C</span></div>
      </div>
      <div class="panel">
        <div class="label">Humidity</div>
        <div class="value"><span id="humidity">--</span> <span class="unit">%</span></div>
      </div>
      <div class="panel">
        <div class="label">Messages</div>
        <div class="value" id="messages">0</div>
      </div>
      <div class="panel">
        <div class="label">Last Update</div>
        <div class="value" style="font-size: 22px;" id="lastUpdate">--</div>
      </div>
    </section>

    <section class="wide">
      <div class="panel">
        <div class="label">Realtime Temperature Trend</div>
        <canvas id="chart" width="900" height="320"></canvas>
      </div>
      <div class="panel">
        <div class="label">Recent Readings</div>
        <table>
          <thead>
            <tr><th>Time</th><th>Temp</th><th>Hum</th></tr>
          </thead>
          <tbody id="history"></tbody>
        </table>
      </div>
    </section>

    <section class="meta">
      <div class="panel">
        <div class="label">Serial Communication</div>
        <div class="small">USB serial, 9600 baud, format <strong>T:25.4,H:61.0</strong></div>
        <div class="small" id="serialStatus"></div>
      </div>
      <div class="panel">
        <div class="label">MQTT Transmission</div>
        <div class="small">Broker <strong>{{ broker }}</strong>, topics <strong>{{ temp_topic }}</strong> and <strong>{{ hum_topic }}</strong></div>
        <div class="small" id="mqttStatus"></div>
      </div>
    </section>
  </main>

  <script>
    const chart = document.getElementById("chart");
    const ctx = chart.getContext("2d");

    function setText(id, value) {
      document.getElementById(id).textContent = value;
    }

    function drawChart(history) {
      ctx.clearRect(0, 0, chart.width, chart.height);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, chart.width, chart.height);
      ctx.strokeStyle = "#d9e2e7";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = 24 + i * 66;
        ctx.beginPath();
        ctx.moveTo(44, y);
        ctx.lineTo(chart.width - 18, y);
        ctx.stroke();
      }
      if (!history.length) return;

      const values = history.map(item => item.temperature);
      let min = Math.min(...values);
      let max = Math.max(...values);
      if (min === max) { min -= 1; max += 1; }
      const left = 44;
      const right = chart.width - 18;
      const top = 24;
      const bottom = chart.height - 32;
      const span = Math.max(history.length - 1, 1);

      ctx.strokeStyle = "#0f766e";
      ctx.lineWidth = 3;
      ctx.beginPath();
      history.forEach((item, index) => {
        const x = left + (index / span) * (right - left);
        const y = bottom - ((item.temperature - min) / (max - min)) * (bottom - top);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      ctx.fillStyle = "#0f766e";
      history.forEach((item, index) => {
        const x = left + (index / span) * (right - left);
        const y = bottom - ((item.temperature - min) / (max - min)) * (bottom - top);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      });

      ctx.fillStyle = "#607080";
      ctx.font = "13px Arial";
      ctx.fillText(max.toFixed(1) + " C", 4, top + 4);
      ctx.fillText(min.toFixed(1) + " C", 4, bottom);
    }

    function render(data) {
      setText("temperature", data.temperature === null ? "--" : data.temperature.toFixed(1));
      setText("humidity", data.humidity === null ? "--" : data.humidity.toFixed(1));
      setText("messages", data.messages);
      setText("lastUpdate", data.last_update || "--");
      setText("serialStatus", data.serial_status + (data.serial_port ? " (" + data.serial_port + ")" : ""));
      setText("mqttStatus", data.mqtt_status);
      setText("liveStatus", data.last_update ? "Live data received" : "Waiting for Arduino data");

      const rows = data.history.slice(-10).reverse().map(item => `
        <tr>
          <td>${item.time.split(" ").pop()}</td>
          <td>${item.temperature.toFixed(1)} C</td>
          <td>${item.humidity.toFixed(1)} %</td>
        </tr>
      `).join("");
      document.getElementById("history").innerHTML = rows || "<tr><td colspan='3'>No readings yet</td></tr>";
      drawChart(data.history);
    }

    async function poll() {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        render(await response.json());
      } catch (error) {
        setText("liveStatus", "Dashboard disconnected");
      }
    }

    poll();
    setInterval(poll, 1000);
  </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(
        DASHBOARD_HTML,
        broker=escape(f"{MQTT_BROKER}:{MQTT_PORT}"),
        temp_topic=escape(MQTT_TOPIC),
        hum_topic=escape(MQTT_TOPIC_HUM),
    )


@app.route("/api/state")
def api_state():
    return jsonify(snapshot())


def main():
    print(f"Dashboard: http://127.0.0.1:{DASHBOARD_PORT}")
    print(f"MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"MQTT topics: {MQTT_TOPIC}, {MQTT_TOPIC_HUM}")
    print(f"Serial ports: {', '.join(serial_ports())}")

    threading.Thread(target=mqtt_worker, daemon=True).start()
    threading.Thread(target=serial_worker, daemon=True).start()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, threaded=True)


if __name__ == "__main__":
    main()
