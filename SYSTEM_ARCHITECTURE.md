# DHT11 Temperature Monitoring System

## System Architecture Diagram

```text
+--------------------+      data wire       +--------------------+
| DHT11 sensor        | -------------------> | Arduino Uno        |
| temperature sensor  |                      | reads temperature  |
+--------------------+                      +---------+----------+
                                                     |
                                                     | I2C LCD communication
                                                     v
                                            +--------------------+
                                            | 16x2 LCD display   |
                                            | row 1: name        |
                                            | row 2: temperature |
                                            +--------------------+
                                                     |
                                                     | USB serial communication
                                                     | 9600 baud
                                                     | format: T:25.4,H:61.0
                                                     v
                                            +--------------------+
                                            | PC Python client   |
                                            | reads serial data  |
                                            | displays realtime  |
                                            +---------+----------+
                                                     |
                                                     | MQTT publish
                                                     v
                                            +--------------------+
                                            | VPS MQTT broker    |
                                            | 157.173.101.159    |
                                            +--------------------+
```

## Arduino Uno Program

File: `DHT11.ino`

Functions implemented:

- Reads temperature and humidity from DHT11 on Arduino pin `2`.
- Displays candidate name `UHIRIWE Chrisostom` on LCD row 1.
- Scrolls row 1 horizontally because the name is longer than 16 characters.
- Displays temperature on LCD row 2.
- Sends readings to the PC through USB serial communication.

Serial communication settings:

- Communication name: USB serial communication between Arduino Uno and PC
- Baud rate: `9600`
- Serial message format: `T:<temperature>,H:<humidity>`
- Example: `T:25.4,H:61.0`

## PC Monitoring and MQTT Transmission

File: `pc_monitor.py`

Functions implemented:

- Reads incoming serial data from Arduino.
- Extracts temperature and humidity values.
- Displays readings in realtime in the terminal.
- Publishes the received values to the MQTT broker on the VPS.

MQTT settings:

- Broker host: `157.173.101.159`
- Broker port: `1883`
- Temperature topic: `dht11/temperature`
- Humidity topic: `dht11/humidity`

## Run Commands

Install Python libraries:

```bash
python3 -m pip install -r requirements.txt
```

Run PC monitor using the default serial port `/dev/ttyUSB0`:

```bash
python3 pc_monitor.py
```

Run PC monitor with another serial port:

```bash
python3 pc_monitor.py /dev/ttyACM0
```

