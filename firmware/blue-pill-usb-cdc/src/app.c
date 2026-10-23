#include "app.h"

#include <stdio.h>
#include <string.h>

void app_init(app_t *app) { memset(app, 0, sizeof(*app)); app->led_on = true; }

void app_receive_irq(app_t *app, const uint8_t *data, size_t size) {
    for (size_t i = 0; i < size; ++i) {
        uint16_t next = (uint16_t)((app->rx_head + 1u) % APP_RX_CAPACITY);
        if (next == app->rx_tail) {
            ++app->rx_drops;
        } else {
            app->rx[app->rx_head] = data[i];
            app->rx_head = next;
        }
    }
}

void app_link(app_t *app, bool configured, uint32_t now_ms) {
    if (app->linked == configured) return;
    app->linked = configured;
    app->rx_tail = app->rx_head;
    app->line_len = 0;
    app->line_overflow = false;
    app->reply_tail = app->reply_head;
    if (configured) app->next_heartbeat_ms = now_ms + 500u;
}

static void queue_reply(app_t *app, const char *value) {
    uint8_t next = (uint8_t)((app->reply_head + 1u) % APP_REPLY_CAPACITY);
    if (next == app->reply_tail) {
        ++app->parse_drops;
        return;
    }
    snprintf(app->replies[app->reply_head], APP_TX_CAPACITY, "%s\r\n", value);
    app->reply_head = next;
}

static void command(app_t *app, uint32_t now_ms) {
    char response[APP_TX_CAPACITY];
    ++app->count;
    app->line[app->line_len] = '\0';
    if (app->line_overflow) {
        queue_reply(app, "ERR LINE_TOO_LONG");
    } else if (strcmp(app->line, "ID") == 0) {
        queue_reply(app, "ID PLASMA_BLUE_PILL_CDC/" APP_VERSION);
    } else if (strcmp(app->line, "PING") == 0) {
        queue_reply(app, "PONG");
    } else if (strcmp(app->line, "LED ON") == 0) {
        app->led_manual = true;
        app->led_on = true;
        queue_reply(app, "LED ON");
    } else if (strcmp(app->line, "LED OFF") == 0) {
        app->led_manual = true;
        app->led_on = false;
        queue_reply(app, "LED OFF");
    } else if (strcmp(app->line, "LED AUTO") == 0) {
        app->led_manual = false;
        app->led_on = true;
        app->led_last_ms = now_ms;
        queue_reply(app, "LED AUTO");
    } else if (strcmp(app->line, "UPTIME") == 0) {
        snprintf(response, sizeof(response), "UPTIME %lu", (unsigned long)now_ms);
        queue_reply(app, response);
    } else if (strcmp(app->line, "COUNT") == 0) {
        snprintf(response, sizeof(response), "COUNT %lu", (unsigned long)app->count);
        queue_reply(app, response);
    } else if (strcmp(app->line, "RX_DROPS") == 0) {
        snprintf(response, sizeof(response), "RX_DROPS %lu", (unsigned long)(app->rx_drops + app->parse_drops));
        queue_reply(app, response);
    } else if (app->line_len != 0u) {
        queue_reply(app, "ERR UNKNOWN_COMMAND");
    }
    app->line_len = 0;
    app->line_overflow = false;
}

void app_process(app_t *app, uint32_t now_ms) {
    /* Independent of link/TX state; unsigned elapsed time survives tick wrap. */
    if (!app->led_manual && (uint32_t)(now_ms - app->led_last_ms) >= 500u) {
        uint32_t periods = (uint32_t)(now_ms - app->led_last_ms) / 500u;
        if (periods & 1u) app->led_on = !app->led_on;
        app->led_last_ms += periods * 500u;
    }
    while (app->rx_tail != app->rx_head) {
        uint8_t c = app->rx[app->rx_tail];
        app->rx_tail = (uint16_t)((app->rx_tail + 1u) % APP_RX_CAPACITY);
        if (c == '\n') {
            command(app, now_ms);
        } else if (c != '\r') {
            if (app->line_len + 1u < APP_LINE_CAPACITY) {
                app->line[app->line_len++] = (char)c;
            } else {
                app->line_overflow = true;
                ++app->parse_drops;
            }
        }
    }
}

size_t app_next(app_t *app, uint32_t now_ms, char *out, size_t capacity, bool *heartbeat) {
    if (!app->linked || capacity == 0u) return 0;
    if (app->reply_tail != app->reply_head) {
        size_t length = strlen(app->replies[app->reply_tail]);
        if (length >= capacity) return 0;
        memcpy(out, app->replies[app->reply_tail], length);
        *heartbeat = false;
        return length;
    }
    if ((int32_t)(now_ms - app->next_heartbeat_ms) < 0) return 0;
    int length = snprintf(out, capacity, "HB version=%s seq=%lu uptime_ms=%lu\r\n",
                          APP_VERSION, (unsigned long)(app->sequence + 1u),
                          (unsigned long)now_ms);
    if (length < 0 || (size_t)length >= capacity) return 0;
    *heartbeat = true;
    return (size_t)length;
}

void app_sent(app_t *app, uint32_t now_ms, bool heartbeat) {
    if (heartbeat) {
        ++app->sequence;
        app->next_heartbeat_ms = now_ms + 500u;
    } else if (app->reply_tail != app->reply_head) {
        app->reply_tail = (uint8_t)((app->reply_tail + 1u) % APP_REPLY_CAPACITY);
    }
}
