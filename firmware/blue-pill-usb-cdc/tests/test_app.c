#include "app.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void rx(app_t *app, const char *text) {
    app_receive_irq(app, (const uint8_t *)text, strlen(text));
}

static void expect_reply(app_t *app, uint32_t now, const char *expected) {
    char output[APP_TX_CAPACITY];
    bool heartbeat = true;
    app_process(app, now);
    size_t size = app_next(app, now, output, sizeof(output), &heartbeat);
    assert(size == strlen(expected));
    assert(memcmp(output, expected, size) == 0);
    assert(!heartbeat);
    app_sent(app, now, false);
}

int main(void) {
    app_t app;
    char output[APP_TX_CAPACITY];
    bool heartbeat = false;
    app_init(&app);
    assert(app_next(&app, 1000, output, sizeof(output), &heartbeat) == 0);
    app_link(&app, true, 1000);
    assert(app_next(&app, 1499, output, sizeof(output), &heartbeat) == 0);
    size_t size = app_next(&app, 1500, output, sizeof(output), &heartbeat);
    assert(heartbeat && size != 0 && strcmp(output, "HB version=0.1 seq=1 uptime_ms=1500\r\n") == 0);
    /* BUSY: without app_sent(), the same frame remains pending. */
    size = app_next(&app, 1700, output, sizeof(output), &heartbeat);
    assert(heartbeat && strncmp(output, "HB version=0.1 seq=1 ", 21) == 0);
    app_sent(&app, 1700, true);
    assert(app_next(&app, 2199, output, sizeof(output), &heartbeat) == 0);
    rx(&app, "ID\r\nPING\nLED ON\nUPTIME\nCOUNT\nRX_DROPS\nLED OFF\n");
    expect_reply(&app, 2100, "ID PLASMA_BLUE_PILL_CDC/0.1\r\n");
    expect_reply(&app, 2100, "PONG\r\n");
    expect_reply(&app, 2100, "LED ON\r\n");
    expect_reply(&app, 2100, "UPTIME 2100\r\n");
    expect_reply(&app, 2100, "COUNT 5\r\n");
    expect_reply(&app, 2100, "RX_DROPS 0\r\n");
    expect_reply(&app, 2100, "LED OFF\r\n");
    assert(!app.led_on);
    size = app_next(&app, 2200, output, sizeof(output), &heartbeat);
    assert(heartbeat && size != 0 && strstr(output, "seq=2") != NULL);
    app_sent(&app, 2200, true);
    app_link(&app, false, 2300);
    assert(app_next(&app, 5000, output, sizeof(output), &heartbeat) == 0);
    app_link(&app, true, 5000);
    assert(app_next(&app, 5499, output, sizeof(output), &heartbeat) == 0);
    assert(app_next(&app, 5500, output, sizeof(output), &heartbeat) != 0);
    assert(strstr(output, "seq=3") != NULL);
    app_sent(&app, 5500, true);
    assert(app_next(&app, 5999, output, sizeof(output), &heartbeat) == 0);
    assert(app_next(&app, 6000, output, sizeof(output), &heartbeat) != 0);
    assert(heartbeat && strstr(output, "seq=4") != NULL);
    /* RX parsing and replies continue while an unsolicited heartbeat is due. */
    app_t concurrent;
    app_init(&concurrent);
    app_link(&concurrent, true, 1000);
    rx(&concurrent, "PING\n");
    expect_reply(&concurrent, 1500, "PONG\r\n");
    assert(app_next(&concurrent, 1500, output, sizeof(output), &heartbeat) != 0);
    assert(heartbeat && strstr(output, "seq=1") != NULL);
    rx(&concurrent, "LED ");
    app_process(&concurrent, 1500);
    rx(&concurrent, "ON\n");
    expect_reply(&concurrent, 1500, "LED ON\r\n");
    assert(concurrent.led_on);
    rx(&concurrent, "LED OFF\n");
    expect_reply(&concurrent, 1500, "LED OFF\r\n");
    assert(!concurrent.led_on);
    /* Tick wrap and RX overflow are bounded. */
    app_init(&app);
    app_link(&app, true, UINT32_MAX - 100u);
    assert(app_next(&app, 399u, output, sizeof(output), &heartbeat) != 0);
    uint8_t flood[300];
    memset(flood, 'X', sizeof(flood));
    app_receive_irq(&app, flood, sizeof(flood));
    assert(app.rx_drops == 45u);
    app_process(&app, 400u);
    rx(&app, "\n");
    expect_reply(&app, 400u, "ERR LINE_TOO_LONG\r\n");
    /* Autonomous LED: unconfigured boot, connection, CDC busy, manual and wrap. */
    app_init(&app);
    assert(app.led_on && !app.led_manual);
    app_process(&app, 499u);
    assert(app.led_on);
    app_process(&app, 500u);
    assert(!app.led_on);
    app_link(&app, true, 600u);
    app_process(&app, 1000u);
    assert(app.led_on);
    assert(app_next(&app, 1099u, output, sizeof(output), &heartbeat) == 0);
    assert(app_next(&app, 1100u, output, sizeof(output), &heartbeat) != 0);
    assert(heartbeat); /* LED timing has not moved the CDC deadline. */
    app_process(&app, 1500u); /* TX still busy: LED continues. */
    assert(!app.led_on);
    rx(&app, "LED ON\n");
    expect_reply(&app, 1500u, "LED ON\r\n");
    app_process(&app, 2500u);
    assert(app.led_on && app.led_manual);
    rx(&app, "LED OFF\n");
    expect_reply(&app, 2500u, "LED OFF\r\n");
    app_link(&app, false, 2500u);
    app_process(&app, 3500u);
    assert(!app.led_on && app.led_manual);
    app_link(&app, true, UINT32_MAX - 100u);
    rx(&app, "LED AUTO\n");
    expect_reply(&app, UINT32_MAX - 100u, "LED AUTO\r\n");
    assert(app.led_on && !app.led_manual);
    app_process(&app, 398u);
    assert(app.led_on);
    app_process(&app, 399u);
    assert(!app.led_on);
    app_process(&app, 1399u); /* Two missed periods retain phase. */
    assert(!app.led_on);
    puts("app host tests PASS");
    return 0;
}
