#ifndef PLASMA_CDC_APP_H
#define PLASMA_CDC_APP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define APP_VERSION "0.1"
#define APP_RX_CAPACITY 256u
#define APP_REPLY_CAPACITY 8u
#define APP_LINE_CAPACITY 48u
#define APP_TX_CAPACITY 96u

typedef struct {
    volatile uint16_t rx_head;
    volatile uint16_t rx_tail;
    uint8_t rx[APP_RX_CAPACITY];
    volatile uint32_t rx_drops;
    uint32_t parse_drops;
    char line[APP_LINE_CAPACITY];
    uint8_t line_len;
    bool line_overflow;
    char replies[APP_REPLY_CAPACITY][APP_TX_CAPACITY];
    uint8_t reply_head;
    uint8_t reply_tail;
    uint32_t count;
    uint32_t sequence;
    uint32_t next_heartbeat_ms;
    bool linked;
    bool led_on;
} app_t;

void app_init(app_t *app);
void app_receive_irq(app_t *app, const uint8_t *data, size_t size);
void app_link(app_t *app, bool configured, uint32_t now_ms);
void app_process(app_t *app, uint32_t now_ms);
/* Called only when the CDC IN endpoint is idle. Output stays owned by caller until transfer completion. */
size_t app_next(app_t *app, uint32_t now_ms, char *out, size_t capacity, bool *heartbeat);
void app_sent(app_t *app, uint32_t now_ms, bool heartbeat);

#endif
