/*
 * ============================================================================
 * ESP8266 PASSIVE BUZZER 5V ALARM SYSTEM FOR DRIVER DROWSINESS DETECTION
 * Bo mạch hỗ trợ chuẩn: NodeMCU 1.0 (ESP-12E Module), Wemos D1 Mini, ESP8266
 * Linh kiện: Còi Buzzer thụ động 5V (Passive Buzzer)
 * ============================================================================
 * SƠ ĐỒ ĐẤU DÂY CHO NODEMCU 1.0 (ESP-12E):
 * 1. Nếu dùng MODULE BUZZER 3 CHÂN (VCC, GND, I/O hoặc SIG):
 *    - Chân VCC  --> Nối chân VIN (nguồn 5V từ cổng USB) của NodeMCU
 *    - Chân GND  --> Nối chân GND của NodeMCU
 *    - Chân I/O  --> Nối chân D7 (hoặc D2) của NodeMCU
 *
 * 2. Nếu dùng CÒI BUZZER RỜI 2 CHÂN (Dương +, Âm -):
 *    - Chân Âm (-)  --> Nối chân GND của NodeMCU
 *    - Chân Dương (+)-> Nối chân D7 (hoặc D2) của NodeMCU
 * ============================================================================
 * PHƯƠNG THỨC KẾT NỐI VỚI MÁY TÍNH:
 * - Cách 1 (Khuyên dùng): Cắm cáp Micro-USB nối NodeMCU với máy tính (Serial COM).
 * - Cách 2: Qua mạng Wi-Fi (HTTP Web Server).
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// ==========================================
// 1. CẤU HÌNH PHẦN CỨNG & CHÂN KẾT NỐI (NODEMCU 1.0)
// ==========================================
// Hỗ trợ đồng thời cả chân D7 (GPIO 13) và D2 (GPIO 4) để cắm chân nào cũng kêu:
const int BUZZER_PIN_D7 = D7; // Chân D7 trên NodeMCU
const int BUZZER_PIN_D2 = D2; // Chân D2 trên NodeMCU

// ==========================================
// 2. CẤU HÌNH WI-FI (TÙY CHỌN NẾU DÙNG KHÔNG DÂY)
// ==========================================
#define ENABLE_WIFI false // Đặt true nếu muốn dùng không dây qua Wi-Fi

const char* ssid     = "KTX TANG 3";     // Tên Wi-Fi (nếu bật Wi-Fi)
const char* password = "thachbich@03"; // Mật khẩu Wi-Fi

ESP8266WebServer server(80);

// ==========================================
// 3. BIẾN TRẠNG THÁI BÁO ĐỘNG (NON-BLOCKING)
// ==========================================
enum AlarmState {
  STATE_IDLE,
  STATE_BEEP,
  STATE_ALARM
};

AlarmState currentState = STATE_IDLE;
unsigned long stateStartTime = 0;
unsigned long lastToneUpdate = 0;
int currentFreq = 1000;
int freqStep = 50;

// Hàm phát tần số âm thanh đồng thời lên cả D7 và D2
void setBuzzerSound(int freq) {
  if (freq <= 0) {
    noTone(BUZZER_PIN_D7);
    analogWrite(BUZZER_PIN_D2, 0);
    digitalWrite(BUZZER_PIN_D7, LOW);
    digitalWrite(BUZZER_PIN_D2, LOW);
  } else {
    // Phát xung tone chuẩn trên D7
    tone(BUZZER_PIN_D7, freq);
    // Đồng thời phát xung PWM 50% cùng tần số trên D2
    analogWriteFreq(freq);
    analogWrite(BUZZER_PIN_D2, 512);
  }
}

// Hàm tắt còi an toàn
void stopBuzzer() {
  setBuzzerSound(0);
  digitalWrite(LED_BUILTIN, HIGH); // Tắt đèn LED trên bo mạch (NodeMCU active LOW)
  currentState = STATE_IDLE;
}

// Hàm kích hoạt tiếng bíp ngắn (nhắc nhở khi ngáp)
void startBeep() {
  currentState = STATE_BEEP;
  stateStartTime = millis();
  digitalWrite(LED_BUILTIN, LOW); // Bật đèn LED xanh trên bo để người dùng thấy tín hiệu
  setBuzzerSound(1800);           // Phát âm thanh 1800Hz
}

// Hàm kích hoạt còi hú khẩn cấp (khi ngủ gật)
void startAlarm() {
  currentState = STATE_ALARM;
  currentFreq = 1200;
  freqStep = 60;
  lastToneUpdate = millis();
  digitalWrite(LED_BUILTIN, LOW);
  setBuzzerSound(currentFreq);
}

// ==========================================
// 4. XỬ LÝ LỆNH TỪ SERIAL (CÁP USB)
// ==========================================
void handleSerialCommands() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "ALARM_ON" || cmd == "ALARM" || cmd == "1") {
      startAlarm();
      Serial.println("[ESP8266] ACK: ALARM_ON");
    } else if (cmd == "ALARM_OFF" || cmd == "STOP" || cmd == "0") {
      stopBuzzer();
      Serial.println("[ESP8266] ACK: ALARM_OFF");
    } else if (cmd == "BEEP" || cmd == "2") {
      startBeep();
      Serial.println("[ESP8266] ACK: BEEP");
    } else if (cmd == "TEST") {
      startBeep();
      Serial.println("[ESP8266] ACK: TEST_OK");
    }
  }
}

// ==========================================
// 5. XỬ LÝ LỆNH TỪ HTTP SERVER (WI-FI)
// ==========================================
void handleHttp() {
  server.on("/alarm/on", HTTP_GET, []() {
    startAlarm();
    server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"ALARM_ON\"}");
  });

  server.on("/alarm/off", HTTP_GET, []() {
    stopBuzzer();
    server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"ALARM_OFF\"}");
  });

  server.on("/beep", HTTP_GET, []() {
    startBeep();
    server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"BEEP\"}");
  });

  server.on("/status", HTTP_GET, []() {
    String stateStr = (currentState == STATE_ALARM) ? "ALARM" : (currentState == STATE_BEEP ? "BEEP" : "IDLE");
    server.send(200, "application/json", "{\"status\":\"ok\",\"state\":\"" + stateStr + "\"}");
  });
}

// ==========================================
// 6. SETUP
// ==========================================
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH); // Tắt LED lúc đầu (Active LOW trên NodeMCU)

  pinMode(BUZZER_PIN_D7, OUTPUT);
  pinMode(BUZZER_PIN_D2, OUTPUT);
  stopBuzzer();

  Serial.begin(115200);
  delay(100);
  Serial.println("\n--- ESP8266 PASSIVE BUZZER ALARM SYSTEM ---");
  Serial.println("San sang nhan lenh qua Serial: ALARM_ON / ALARM_OFF / BEEP");

  if (ENABLE_WIFI) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    Serial.print("Dang ket noi Wi-Fi");
    int count = 0;
    while (WiFi.status() != WL_CONNECTED && count < 25) {
      delay(500);
      Serial.print(".");
      count++;
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nDa ket noi Wi-Fi thanh cong!");
      Serial.print("Dia chi IP ESP8266: http://");
      Serial.println(WiFi.localIP());
      handleHttp();
      server.begin();
      Serial.println("HTTP Webhook Server da khoi dong!");
    } else {
      Serial.println("\nKhong ket noi duoc Wi-Fi, su dung che do Serial USB.");
    }
  }

  // Nháy đèn LED và kêu 2 tiếng bíp khởi động trên cả D7 và D2
  digitalWrite(LED_BUILTIN, LOW);
  setBuzzerSound(2000);
  delay(120);
  digitalWrite(LED_BUILTIN, HIGH);
  setBuzzerSound(0);
  delay(100);
  digitalWrite(LED_BUILTIN, LOW);
  setBuzzerSound(2000);
  delay(120);
  digitalWrite(LED_BUILTIN, HIGH);
  setBuzzerSound(0);
}

// ==========================================
// 7. LOOP CHÍNH (HOÀN TOÀN KHÔNG DÙNG DELAY)
// ==========================================
void loop() {
  // 1. Nhận lệnh từ Serial (Cáp USB)
  handleSerialCommands();

  // 2. Nhận lệnh từ HTTP (nếu bật Wi-Fi)
  if (ENABLE_WIFI && WiFi.status() == WL_CONNECTED) {
    server.handleClient();
  }

  // 3. Xử lý âm thanh theo trạng thái mà không chặn luồng
  unsigned long now = millis();

  if (currentState == STATE_BEEP) {
    // Tiếng bíp kéo dài 200ms rồi tự tắt
    if (now - stateStartTime >= 200) {
      stopBuzzer();
    }
  } else if (currentState == STATE_ALARM) {
    // Hiệu ứng còi hú biến tần (Police Siren) dồn dập
    if (now - lastToneUpdate >= 12) {
      lastToneUpdate = now;
      currentFreq += freqStep;
      if (currentFreq >= 2600) {
        currentFreq = 2600;
        freqStep = -70;
      } else if (currentFreq <= 900) {
        currentFreq = 900;
        freqStep = 70;
      }
      setBuzzerSound(currentFreq);
    }
  }
}

