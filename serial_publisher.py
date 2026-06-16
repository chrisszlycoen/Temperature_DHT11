import sys
import time

import paho.mqtt.client as mqtt
import serial


BAUD_RATE = 9600
MQTT_BROKER = "157.173.101.159"
MQTT_PORT = 1883
MQTT_TOPIC = "dht11/temperature"

DEFAULT_SERIAL_PORTS = [
    "/dev/ttyUSB0",
    "/dev/ttyACM0",
    "/dev/ttyUSB1",
    "/dev/ttyACM1",
]


def serial_ports():
    if len(sys.argv) > 1:
        return [sys.argv[1]]
    return DEFAULT_SERIAL_PORTS


def parse_reading(line):
    if not line.startswith("T:"):
        return None

    if ",H:" in line:
        temp_part, hum_part = line.split(",", 1)
        return float(temp_part.replace("T:", "")), float(hum_part.replace("H:", ""))

    return float(line.replace("T:", "")), None


def connect_mqtt():
    client = mqtt.Client()
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()
            print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
            return client
        except Exception as exc:
            print(f"[MQTT] Connection failed: {exc}")
            time.sleep(5)


def main():
    mqtt_client = connect_mqtt()
    ports = serial_ports()
    print(f"[SERIAL] Watching: {', '.join(ports)}")

    while True:
        for port in ports:
            try:
                print(f"[SERIAL] Opening {port} @ {BAUD_RATE}")
                with serial.Serial(port, BAUD_RATE, timeout=1) as ser:
                    time.sleep(2)
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
                            print(f"[RAW] {line}")
                            continue

                        temp, hum = reading
                        mqtt_client.publish(MQTT_TOPIC, f"{temp:.1f}")
                        if hum is not None:
                            mqtt_client.publish("dht11/humidity", f"{hum:.1f}")
                            print(f"[DATA] Temp: {temp:.1f} C | Humidity: {hum:.1f} %")
                        else:
                            print(f"[DATA] Temp: {temp:.1f} C")
            except serial.SerialException as exc:
                print(f"[SERIAL] {port} not available: {exc}")
            except Exception as exc:
                print(f"[ERROR] {exc}")

        time.sleep(3)


if __name__ == "__main__":
    main()
