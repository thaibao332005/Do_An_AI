/*
 * ============================================================================
 * ESP32-CAM Video Streamer & Snapshot Server for Driver Drowsiness Detection
 * Bo mạch hỗ trợ: AI-Thinker ESP32-CAM (OV2640 Camera)
 * ============================================================================
 * CÁC ENDPOINT HỖ TRỢ:
 * - Luồng MJPEG: http://<IP>:81/stream
 * - Chụp Snapshot: http://<IP>/capture (Chống nghẽn socket 100%)
 * - Xem trên web:  http://<IP>
 * ============================================================================
 */

#include "Arduino.h"
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include "img_converters.h"
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"
#include <WiFi.h>

// ==========================================
// 1. CẤU HÌNH THÔNG TIN MẠNG WI-FI
// ==========================================
// false: Kết nối vào Wi-Fi KTX / Router phòng (Khuyên dùng)
// true:  ESP32 Tự phát Wi-Fi riêng "ESP32-CAM-AI" (IP: 192.168.4.1)
#define USE_AP_MODE false

const char *ssid = "KTX TANG 3";       // Tên Wi-Fi KTX
const char *password = "thachbich@03"; // Mật khẩu Wi-Fi KTX

// Thông tin Wi-Fi do ESP32 tự phát (nếu USE_AP_MODE = true hoặc khi Wi-Fi KTX mất kết nối)
const char *ap_ssid = "ESP32-CAM-AI";
const char *ap_password = "12345678";

// ==========================================
// 2. PINOUT CHO MODULE AI-THINKER ESP32-CAM
// ==========================================
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27

#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

#define PART_BOUNDARY "123456789000000000000987654321"
static const char *_STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char *_STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char *_STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t camera_httpd = NULL;
httpd_handle_t stream_httpd = NULL;

// 1. Xử lý luồng MJPEG Video (/stream)
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t *_jpg_buf = NULL;
  char *part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) {
    return res;
  }

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }
    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (res != ESP_OK) {
      break;
    }
  }
  return res;
}

// 2. Xử lý chụp ảnh đơn Snapshot (/capture) - Chống nghẽn socket 100%
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// 3. Xử lý giao diện web xem thử trên trình duyệt (/)
static esp_err_t index_handler(httpd_req_t *req) {
  const char* html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>ESP32-CAM</title><style>body{text-align:center;font-family:sans-serif;background:#111;color:#fff;margin-top:20px;}img{max-width:92%;border-radius:10px;box-shadow:0 4px 15px rgba(0,0,0,0.6);}</style></head><body><h2>📷 ESP32-CAM Live View</h2><img src=':81/stream' onerror=\"this.src='/capture?'+Math.random();\"><br><br><p><a href='/capture' style='color:#00D2FF;margin-right:15px;font-size:16px;'>[Chụp ảnh /capture]</a><a href=':81/stream' style='color:#00FF88;font-size:16px;'>[Luồng /stream]</a></p></body></html>";
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, html, strlen(html));
}

void startCameraServer() {
  // Server Port 80: Web UI & /capture Snapshot
  httpd_config_t config_80 = HTTPD_DEFAULT_CONFIG();
  config_80.server_port = 80;
  config_80.ctrl_port = 32768;

  httpd_uri_t index_uri = {.uri = "/", .method = HTTP_GET, .handler = index_handler, .user_ctx = NULL};
  httpd_uri_t capture_uri = {.uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = NULL};

  if (httpd_start(&camera_httpd, &config_80) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    Serial.println("Server Port 80 (Web UI & /capture) da san sang!");
  }

  // Server Port 81: Luong MJPEG Stream
  httpd_config_t config_81 = HTTPD_DEFAULT_CONFIG();
  config_81.server_port = 81;
  config_81.ctrl_port = 32769;

  httpd_uri_t stream_uri = {.uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = NULL};

  if (httpd_start(&stream_httpd, &config_81) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("Stream Server Port 81 (/stream) da san sang!");
  }
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Tat bao loi Brownout khi dien yeu
  Serial.begin(115200);
  Serial.println("\n--- DANG KHOI DONG ESP32-CAM ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA; // 640x480
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA; // 320x240
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Loi khoi tao Camera: 0x%x", err);
    return;
  }

  bool ap_active = false;

  if (USE_AP_MODE) {
    Serial.println("\n--- KHOI DONG CHE DO TU PHAT WI-FI (ACCESS POINT) ---");
    WiFi.mode(WIFI_AP);
    WiFi.softAP(ap_ssid, ap_password);
    ap_active = true;
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    Serial.print("Dang ket noi Wi-Fi KTX");
    int retry = 0;
    while (WiFi.status() != WL_CONNECTED && retry < 30) {
      delay(500);
      Serial.print(".");
      retry++;
    }
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("\n[CANH BAO] Khong bat duoc Wi-Fi KTX! Tu dong chuyen sang TU PHAT AP...");
      WiFi.disconnect();
      WiFi.mode(WIFI_AP);
      WiFi.softAP(ap_ssid, ap_password);
      ap_active = true;
    } else {
      Serial.println("\nDa ket noi Wi-Fi thanh cong!");
    }
  }

  startCameraServer();

  Serial.println("\n==================================================");
  if (ap_active) {
    Serial.println("ESP32 DANG TU PHAT WI-FI:");
    Serial.print("- Ten Wi-Fi (SSID): "); Serial.println(ap_ssid);
    Serial.print("- Mat khau:         "); Serial.println(ap_password);
    Serial.print(">>> LINK DÁN VÀO APP: http://");
    Serial.print(WiFi.softAPIP());
    Serial.println(":81/stream");
    Serial.print(">>> HOẶC DÙNG SNAPSHOT: http://");
    Serial.print(WiFi.softAPIP());
    Serial.println("/capture");
  } else {
    Serial.println("ESP32 DA VAO WI-FI KTX:");
    Serial.print(">>> LINK 1 (STREAM):   http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81/stream");
    Serial.print(">>> LINK 2 (SNAPSHOT): http://");
    Serial.print(WiFi.localIP());
    Serial.println("/capture  <-- KHUYÊN DÙNG, CHỐNG NGHẼN 100%");
    Serial.print(">>> XEM TRÊN WEB:      http://");
    Serial.println(WiFi.localIP());
  }
  Serial.println("==================================================\n");
}

void loop() { delay(10000); }
