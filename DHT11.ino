#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <string.h>

#define DHTPIN 2
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);

const char* myName = "UHIRIWE Chrisostom";
const int nameLen = strlen(myName);
int scrollOffset = 0;
unsigned long lastScroll = 0;
const int scrollInterval = 300;

unsigned long lastRead = 0;
const int readInterval = 2000;

float temperature = 0.0;

void printRow(int row, const char* text) {
  lcd.setCursor(0, row);
  bool padding = false;
  for (int i = 0; i < 16; i++) {
    if (padding || text[i] == '\0') {
      padding = true;
      lcd.print(" ");
    } else {
      lcd.print(text[i]);
    }
  }
}

void scrollName() {
  if (nameLen <= 16) {
    printRow(0, myName);
  } else {
    char buffer[17];
    const int scrollWidth = nameLen + 4;

    for (int i = 0; i < 16; i++) {
      int idx = (scrollOffset + i) % scrollWidth;
      if (idx < nameLen) {
        buffer[i] = myName[idx];
      } else {
        buffer[i] = ' ';
      }
    }
    buffer[16] = '\0';
    printRow(0, buffer);
    unsigned long now = millis();
    if (now - lastScroll >= scrollInterval) {
      lastScroll = now;
      scrollOffset++;
      if (scrollOffset >= scrollWidth) {
        scrollOffset = 0;
      }
    }
  }
}

void displayTemperature() {
  char tempText[17];
  char valueText[8];
  dtostrf(temperature, 4, 1, valueText);
  snprintf(tempText, sizeof(tempText), "Temp:%s C", valueText);
  printRow(1, tempText);
}

void displaySensorError() {
  printRow(1, "Sensor error");
}

void setup() {
  Serial.begin(9600);
  delay(1500);
  Serial.println("BOOT:DHT11");
  Wire.begin();
  Wire.setWireTimeout(3000, true);
  lcd.init();
  delay(100);
  lcd.clear();
  lcd.backlight();
  dht.begin();

  printRow(0, "DHT11 Starting");
  printRow(1, "Please wait");
  Serial.println("LCD:READY");
  delay(2000);
  lcd.clear();
}

void loop() {
  unsigned long now = millis();

  if (now - lastRead >= readInterval) {
    lastRead = now;
    float t = dht.readTemperature();

    if (!isnan(t)) {
      temperature = t;

      Serial.print("T:");
      Serial.println(temperature, 1);
    } else {
      Serial.println("ERR:DHT11");
    }
  }

  scrollName();
  if (temperature == 0.0) {
    displaySensorError();
  } else {
    displayTemperature();
  }
}
