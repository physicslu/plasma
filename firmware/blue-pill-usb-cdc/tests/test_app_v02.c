#include "app.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if APP_LED_PERIOD_MS != 1000u || APP_HEARTBEAT_PERIOD_MS != 1000u
#error "This test must be compiled for the 1-second v0.2 variant"
#endif

static void rx(app_t *app, const char *command) {
    app_receive_irq(app, (const uint8_t *)command, strlen(command));
}
static void reply(app_t *app, uint32_t now, const char *expected) {
    char output[APP_TX_CAPACITY] = {0};
    bool heartbeat = true;
    app_process(app, now);
    size_t count = app_next(app, now, output, sizeof(output), &heartbeat);
    assert(!heartbeat && count == strlen(expected));
    assert(memcmp(output, expected, count) == 0);
    app_sent(app, now, false);
}
int main(void) {
    app_t app;
    char output[APP_TX_CAPACITY];
    bool heartbeat = false;
    app_init(&app);
    assert(app.led_on);
    app_link(&app, true, 100u);
    app_process(&app, 999u);
    assert(app.led_on);
    app_process(&app, 1000u);
    assert(!app.led_on);
    app_process(&app, 2000u);
    assert(app.led_on);
    assert(app_next(&app, 1099u, output, sizeof(output), &heartbeat) == 0);
    size_t count = app_next(&app, 1100u, output, sizeof(output), &heartbeat);
    assert(heartbeat && count != 0u);
    assert(strcmp(output, "HB version=0.2 seq=1 uptime_ms=1100\r\n") == 0);
    /* TX remains BUSY unless the main loop accepts the packet. */
    app_next(&app, 1900u, output, sizeof(output), &heartbeat);
    assert(strstr(output, "seq=1") != NULL);
    app_sent(&app, 1900u, true);
    assert(app_next(&app, 2899u, output, sizeof(output), &heartbeat) == 0);
    assert(app_next(&app, 2900u, output, sizeof(output), &heartbeat) != 0);
    assert(strcmp(output, "HB version=0.2 seq=2 uptime_ms=2900\r\n") == 0);
    app_sent(&app, 2900u, true);

    rx(&app, "ID\nPING\nLED OFF\n");
    reply(&app, 3000u, "ID PLASMA_BLUE_PILL_CDC/0.2\r\n");
    reply(&app, 3000u, "PONG\r\n");
    reply(&app, 3000u, "LED OFF\r\n");
    app_process(&app, 8000u);
    assert(!app.led_on && app.led_manual);
    rx(&app, "LED AUTO\n");
    reply(&app, 8000u, "LED AUTO\r\n");
    assert(app.led_on && !app.led_manual);
    app_process(&app, 8999u);
    assert(app.led_on);
    app_process(&app, 9000u);
    assert(!app.led_on);
    /* USB reset must not stop autonomous LED timing. */
    app_link(&app, false, 9100u);
    app_process(&app, 10000u);
    assert(app.led_on);
    app_link(&app, true, 10000u);
    assert(app_next(&app, 10999u, output, sizeof(output), &heartbeat) == 0);
    assert(app_next(&app, 11000u, output, sizeof(output), &heartbeat) != 0);
    assert(strstr(output, "seq=3") != NULL);

    /* Both timers survive unsigned 32-bit HAL tick rollover. */
    app_init(&app);
    app.led_last_ms = UINT32_MAX - 499u;
    app_link(&app, true, UINT32_MAX - 499u);
    app_process(&app, 499u);
    assert(app.led_on);
    assert(app_next(&app, 499u, output, sizeof(output), &heartbeat) == 0);
    app_process(&app, 500u);
    assert(!app.led_on);
    assert(app_next(&app, 500u, output, sizeof(output), &heartbeat) != 0);
    assert(strstr(output, "version=0.2 seq=1") != NULL);
    puts("app v0.2 host tests PASS");
    return 0;
}
