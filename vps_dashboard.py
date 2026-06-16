import threading
import time
from collections import deque
from html import escape

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string


MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "dht11/temperature"
MQTT_TOPIC_HUM = "dht11/humidity"
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 9272

app = Flask(__name__)
state_lock = threading.Lock()
history = deque(maxlen=80)
state = {
    "temperature": None,
    "humidity": None,
    "mqtt_status": "Connecting",
    "last_update": None,
    "messages": 0,
}


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def snapshot():
    with state_lock:
        data = dict(state)
        data["history"] = list(history)
    return data


def on_connect(client, userdata, flags, rc, *extra):
    with state_lock:
        if rc == 0:
            state["mqtt_status"] = f"Connected to {MQTT_BROKER}:{MQTT_PORT}"
        else:
            state["mqtt_status"] = f"Connection failed rc={rc}"

    if rc == 0:
        client.subscribe([(MQTT_TOPIC, 0), (MQTT_TOPIC_HUM, 0)])
        print(f"[MQTT] Subscribed to {MQTT_TOPIC} and {MQTT_TOPIC_HUM}")


def on_disconnect(client, userdata, rc, *extra):
    if rc != 0:
        with state_lock:
            state["mqtt_status"] = "Disconnected, retrying"


def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8", errors="ignore").strip()
    timestamp = now_text()

    with state_lock:
        if message.topic == MQTT_TOPIC:
            try:
                state["temperature"] = float(payload)
            except ValueError:
                return
        elif message.topic == MQTT_TOPIC_HUM:
            try:
                state["humidity"] = float(payload)
            except ValueError:
                return
        else:
            return

        state["last_update"] = timestamp
        state["messages"] += 1
        if state["temperature"] is not None:
            history.append(
                {
                    "time": timestamp,
                    "temperature": state["temperature"],
                    "humidity": state["humidity"],
                }
            )

    print(f"[{timestamp}] {message.topic}: {payload}")


def mqtt_worker():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever(retry_first_connection=True)
        except Exception as exc:
            with state_lock:
                state["mqtt_status"] = f"Unavailable: {exc}"
            print(f"[MQTT] Unavailable: {exc}")
            time.sleep(5)


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DHT11 Temperature Dashboard</title>
  <style>
    :root {
      font-family: Arial, Helvetica, sans-serif;
      --ink: #172026;
      --muted: #607080;
      --panel: #ffffff;
      --line: #d9e2e7;
      --bg: #eef3f5;
      --accent: #0f766e;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; color: var(--ink); background: var(--bg); }
    header {
      padding: 22px 28px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 24px; line-height: 1.2; }
    .candidate { color: var(--muted); font-size: 14px; margin-top: 4px; }
    main { width: min(1120px, calc(100% - 32px)); margin: 24px auto; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .value { font-size: 36px; font-weight: 700; line-height: 1; }
    .unit { font-size: 18px; color: var(--muted); }
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
    .wide { margin-top: 14px; display: grid; grid-template-columns: 1.2fr .8fr; gap: 14px; }
    canvas { width: 100%; height: 320px; display: block; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
    th { color: var(--muted); font-weight: 700; }
    .meta { margin-top: 14px; }
    .small { font-size: 14px; color: var(--muted); overflow-wrap: anywhere; }
    @media (max-width: 820px) {
      .grid, .wide { grid-template-columns: 1fr; }
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
    <div class="status" id="liveStatus">Waiting for MQTT data</div>
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
        <div class="label">MQTT Messages</div>
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
          <thead><tr><th>Time</th><th>Temp</th><th>Hum</th></tr></thead>
          <tbody id="history"></tbody>
        </table>
      </div>
    </section>

    <section class="meta panel">
      <div class="label">MQTT Transmission</div>
      <div class="small">Broker <strong>{{ broker }}</strong>, topics <strong>{{ temp_topic }}</strong> and <strong>{{ hum_topic }}</strong></div>
      <div class="small" id="mqttStatus"></div>
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
    }

    function render(data) {
      setText("temperature", data.temperature === null ? "--" : data.temperature.toFixed(1));
      setText("humidity", data.humidity === null ? "--" : data.humidity.toFixed(1));
      setText("messages", data.messages);
      setText("lastUpdate", data.last_update || "--");
      setText("mqttStatus", data.mqtt_status);
      setText("liveStatus", data.last_update ? "Live MQTT data received" : "Waiting for MQTT data");

      const rows = data.history.slice(-10).reverse().map(item => `
        <tr>
          <td>${item.time.split(" ").pop()}</td>
          <td>${item.temperature.toFixed(1)} C</td>
          <td>${item.humidity === null ? "--" : item.humidity.toFixed(1) + " %"}</td>
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
    print(f"Dashboard: http://0.0.0.0:{DASHBOARD_PORT}")
    print(f"MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"MQTT topics: {MQTT_TOPIC}, {MQTT_TOPIC_HUM}")
    threading.Thread(target=mqtt_worker, daemon=True).start()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, threaded=True)


if __name__ == "__main__":
    main()
